import chromadb
import torch
import requests
import time
from PIL import Image
from duckduckgo_search import DDGS
from io import BytesIO
from transformers import CLIPModel, CLIPProcessor
from deep_translator import GoogleTranslator
from pathlib import Path
import pymorphy3
from rapidfuzz import fuzz

# === 1. ИНИЦИАЛИЗАЦИЯ ===
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"⚙️ Инициализация движка на: {device}")

client = chromadb.PersistentClient(path=str(Path(__file__).parent.parent.parent / "data" / "chroma_db"))
visual_collection = client.get_collection(name="lemana_products")

print("👁️ Загрузка визуальной модели (CLIP)...")
clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

print("📚 Инициализация морфологического анализатора...")
morph = pymorphy3.MorphAnalyzer()

# === 2. ВСПОМОГАТЕЛЬНАЯ ЛОГИКА ===
def _apply_smart_filter(query_text, raw_results, top_k=5):
    query_words = [w.lower() for w in query_text.split() if len(w) > 2]
    query_normals = [morph.parse(w)[0].normal_form for w in query_words]

    scored_items = []
    metadatas = raw_results.get('metadatas', [[]])[0]
    distances = raw_results.get('distances', [[]])[0]
    ids = raw_results.get('ids', [[]])[0]

    if not metadatas:
        return raw_results

    for item_id, meta, dist in zip(ids, metadatas, distances):
        product_name = meta['name'].lower()
        product_words = [w.strip(',.()"-/') for w in product_name.split() if w.strip(',.()"-/')]
        product_normals = [morph.parse(w)[0].normal_form for w in product_words]

        matched_count = 0
        quality_score = 0

        for qw, qn in zip(query_words, query_normals):
            best_sim = 0
            for pw, pn in zip(product_words, product_normals):
                sim = max(fuzz.ratio(qn, pn), fuzz.ratio(qw, pw))
                if len(pw) > 3 and len(qw) > 3:
                    if pw in qw or qw in pw or pn in qn or qn in pn:
                        sim = max(sim, 90)
                if sim > best_sim:
                    best_sim = sim

            if best_sim >= 80:
                matched_count += 1
                quality_score += best_sim

        total_text_score = (matched_count * 1000) + quality_score

        if total_text_score > 0:
            scored_items.append({
                'id': item_id,
                'meta': meta,
                'distance': dist,
                'score': total_text_score
            })

    scored_items.sort(key=lambda x: (-x['score'], x['distance']))

    filtered_ids = [item['id'] for item in scored_items[:top_k]]
    filtered_metadatas = [item['meta'] for item in scored_items[:top_k]]
    filtered_distances = [item['distance'] for item in scored_items[:top_k]]

    if len(filtered_metadatas) < top_k:
        for item_id, meta, dist in zip(ids, metadatas, distances):
            if item_id not in filtered_ids:
                filtered_ids.append(item_id)
                filtered_metadatas.append(meta)
                filtered_distances.append(dist)
                if len(filtered_metadatas) == top_k:
                    break

    return {
        'ids': [filtered_ids],
        'metadatas': [filtered_metadatas],
        'distances': [filtered_distances]
    }

# === 3. ОСНОВНЫЕ ФУНКЦИИ ПОИСКА ===
def _search_text_only(query_text, filters=None, top_k=5):
    en_query = GoogleTranslator(source='ru', target='en').translate(query_text)

    inputs_txt = clip_processor(text=[en_query], return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        text_emb = clip_model.get_text_features(**inputs_txt).pooler_output
        text_emb = text_emb / torch.norm(text_emb, p=2, dim=-1, keepdim=True)
        text_emb_np = text_emb.cpu().numpy()[0]

    raw_results = visual_collection.query(
        query_embeddings=[text_emb_np.tolist()],
        n_results=2000 if not filters else 50, # Уменьшаем выборку, если есть жесткий фильтр
        where=filters
    )
    return _apply_smart_filter(query_text, raw_results, top_k)


def _search_image_only(image, filters=None, top_k=5):
    # Убрали Image.open(), так как интерфейс уже передает готовый PIL объект
    inputs = clip_processor(images=image, return_tensors="pt").to(device)

    with torch.no_grad():
        img_emb = clip_model.get_image_features(**inputs).pooler_output
        img_emb = img_emb / torch.norm(img_emb, p=2, dim=-1, keepdim=True)
        img_emb_np = img_emb.cpu().numpy()[0]

    results = visual_collection.query(
        query_embeddings=[img_emb_np.tolist()],
        n_results=top_k,
        where=filters
    )
    return results


def _get_image_from_text(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=1))

        if results:
            image_url = results[0]['image']

            response = requests.get(image_url, timeout=5)
            img = Image.open(BytesIO(response.content)).convert("RGB")
            return img
    except Exception as e:
        print(f"Ошибка поиска картинки: {e}")
    return None


def _search_multimodal(image, query_text, filters=None, image_weight=0.7, top_k=5):
    inputs_img = clip_processor(images=image, return_tensors="pt").to(device)

    with torch.no_grad():
        img_emb = clip_model.get_image_features(**inputs_img).pooler_output
        img_emb = img_emb / torch.norm(img_emb, p=2, dim=-1, keepdim=True)

    en_query = GoogleTranslator(source='ru', target='en').translate(query_text)
    inputs_txt = clip_processor(text=[en_query], return_tensors="pt", padding=True).to(device)

    with torch.no_grad():
        text_emb = clip_model.get_text_features(**inputs_txt).pooler_output
        text_emb = text_emb / torch.norm(text_emb, p=2, dim=-1, keepdim=True)

    text_weight = 1.0 - image_weight
    combined_emb = (img_emb * image_weight) + (text_emb * text_weight)
    combined_emb = combined_emb / torch.norm(combined_emb, p=2, dim=-1, keepdim=True)
    combined_emb_np = combined_emb.cpu().numpy()[0]

    raw_results = visual_collection.query(
        query_embeddings=[combined_emb_np.tolist()],
        n_results=2000 if not filters else 50,
        where=filters
    )
    return _apply_smart_filter(query_text, raw_results, top_k)


def smart_search(query_text=None, image=None, filters=None, top_k=5):
    if query_text and not image:
        img = _get_image_from_text(query_text)
        print(f"\n[ROUTER] Чистый текстовый поиск (+ фото из Google): '{query_text}', Фильтры: {filters}")
        return _search_multimodal(img, query_text, filters, top_k)

    elif image and not query_text:
        print(f"\n[ROUTER] Чистый поиск по картинке, Фильтры: {filters}")
        return _search_image_only(image, filters, top_k)

    elif query_text and image:
        print(f"\n[ROUTER] Мультимодальный поиск: Фото + Текст '{query_text}', Фильтры: {filters}")
        return _search_multimodal(image, query_text, filters, top_k)

    else:
        return None