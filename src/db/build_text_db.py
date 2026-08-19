import pandas as pd
import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from pathlib import Path


# Указываем пути к твоим файлам
BASE_DIR = Path(__file__).parent.parent.parent
JSONL_PATH = BASE_DIR / "data" / "lem_products.jsonl"
CHROMA_PATH = BASE_DIR / "data" / "chroma_db"


def build_text_collection():
    # === БЛОК 1: Подготовка сырых данных ===
    print("📥 Загружаем каталог товаров...")
    goods = pd.read_json(JSONL_PATH, lines=True)
    goods = goods.drop_duplicates(subset=['url']).reset_index(drop=True)
    goods = goods.dropna(subset=['image_url'])

    # === БЛОК 2: Подключение к ChromaDB ===
    print("🗄️ Подключаемся к базе ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Создаем НОВУЮ коллекцию специально для текстов
    text_collection = client.get_or_create_collection(
        name="lemana_text_products",
        metadata={"hnsw:space": "cosine"}
    )

    # === БЛОК 3: Загрузка семантической языковой модели ===
    print("🧠 Загружаем языковую модель (CPU)...")
    # Используем MiniLM - она специализируется именно на смысле слов (синонимах)
    text_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device='cpu')

    # === БЛОК 4: Пакетная генерация и запись (Батчинг) ===
    batch_size = 2000  # Размер "тележки" для записи

    # Подготавливаем списки данных из датафрейма
    product_names = goods['name'].astype(str).tolist()
    product_prices = goods['price'].astype(float).tolist()
    product_urls = goods['url'].astype(str).tolist()
    product_images = goods['image_url'].astype(str).tolist()

    print(f"🚀 Начинаем создание текстовых векторов для {len(product_names)} товаров...")

    for i in tqdm(range(0, len(product_names), batch_size), desc="Запись в БД"):
        # Отрезаем нужный кусок (батч)
        end_idx = i + batch_size
        batch_names = product_names[i:end_idx]

        # 4.1. Превращаем названия товаров в смысловые векторы
        # Модель сама поймет, что "Триммер бензиновый" это инструмент для травы
        batch_embeddings = text_model.encode(batch_names, normalize_embeddings=True)

        # 4.2. Формируем ID и метаданные
        batch_ids = [f"text_item_{j}" for j in range(i, min(end_idx, len(product_names)))]
        batch_metadatas = [
            {
                "name": product_names[j],
                "price": product_prices[j],
                "url": product_urls[j],
                "image_url": product_images[j]
            }
            for j in range(i, min(end_idx, len(product_names)))
        ]

        # 4.3. Загружаем пачку в ChromaDB
        text_collection.add(
            ids=batch_ids,
            embeddings=batch_embeddings.tolist(),
            metadatas=batch_metadatas
        )

    print("\n🎉 Текстовая коллекция успешно собрана!")


if __name__ == "__main__":
    build_text_collection()