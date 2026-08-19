import os
import chromadb
import numpy as np
import pandas as pd
from tqdm import tqdm
from pathlib import Path

EMB_DIR = Path(__file__).parent.parent.parent / 'data' / 'embeddings'
JSONL_PATH = Path(__file__).parent.parent.parent / 'data' / 'lem_products.jsonl'
CHROMA_PATH = Path(__file__).parent.parent.parent / 'data' / 'chroma_db'
# google-chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_debug"

def build_database():
    # 1. Загружаем и чистим метаданные точно так же, как в Colab
    print("📥 Загружаем jsonl...")
    goods = pd.read_json(JSONL_PATH, lines=True)
    goods = goods.drop_duplicates(subset=['url']).reset_index(drop=True)
    goods = goods.dropna(subset=['image_url'])

    # 2. Инициализируем локальную базу ChromaDB
    print("🗄️ Подключаемся к ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Создаем коллекцию (расстояние cosine идеально для нормализованных векторов CLIP)
    collection = client.get_or_create_collection(
        name="lemana_products",
        metadata={"hnsw:space": "cosine"}
    )

    # 3. Ищем все файлы с эмбеддингами и сортируем их по возрастанию
    emb_files = sorted(
        [f for f in os.listdir(EMB_DIR) if f.startswith('emb_') and f.endswith('.npy')],
        key=lambda x: int(x.split('_')[1].split('.')[0])
    )

    for emb_file in emb_files:
        # Находим парный файл с индексами
        idx_file = emb_file.replace('emb_', 'idx_')
        print(f"\n⚙️ Обрабатываем пару: {emb_file} и {idx_file}")

        # Загружаем массивы в память
        embeddings = np.load(os.path.join(EMB_DIR, emb_file))
        indices = np.load(os.path.join(EMB_DIR, idx_file))

        batch_ids = []
        batch_embeddings = []
        batch_metadatas = []

        # Формируем данные для заливки
        for emb, idx in zip(embeddings, indices):
            row = goods.iloc[idx]

            batch_ids.append(f"item_{idx}")
            batch_embeddings.append(emb.tolist())

            # Сохраняем карточку товара для выдачи пользователю
            batch_metadatas.append({
                "name": str(row['name']),
                "price": float(row['price']),
                "url": str(row['url']),
                "image_url": str(row['image_url'])
            })

        # 4. Заливаем пачку в базу мелкими чанками по 5000 штук
        chunk_size = 5000
        for i in tqdm(range(0, len(batch_ids), chunk_size), desc="Запись в БД"):
            collection.add(
                ids=batch_ids[i:i + chunk_size],
                embeddings=batch_embeddings[i:i + chunk_size],
                metadatas=batch_metadatas[i:i + chunk_size]
            )

    print("\n🎉 Векторная база SmartSearch успешно собрана!")


if __name__ == "__main__":
    build_database()