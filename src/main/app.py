import streamlit as st
from PIL import Image
from search_engine import smart_search

st.set_page_config(page_title="SmartSearch Лемана ПРО", page_icon="🔍", layout="wide")

# === ШАПКА ИНТЕРФЕЙСА ===
st.title("SmartSearch: Мультимодальный поиск 🔍")

st.info("""
📸 **Ищи по фото:** Загрузи картинку детали или инструмента, если не знаешь название.

⌨️ **Ищи по тексту:** Введи название, бренд или цвет.

✨ **Магия мультимодальности:** Загрузи фото и допиши текст (например, фото дрели + текст "зеленого цвета").
""")

# === БОКОВАЯ ПАНЕЛЬ (ФИЛЬТРЫ) ===
st.sidebar.header("Фильтры")
departments = [
    "Все отделы", "Сад", "Стройматериалы", "Столярные изделия", "Электротовары",
    "Инструменты", "Напольные покрытия", "Плитка", "Сантехника", "Водоснабжение",
    "Скобяные изделия", "Краски", "Обои", "Освещение", "Хранение", "Кухни", "Декор"
]

selected_dept = st.sidebar.selectbox("Выберите отдел", departments)

# === ОСНОВНАЯ ЗОНА ПОИСКА ===
col1, col2 = st.columns(2)

with col1:
    text_query = st.text_input("Текстовый запрос", placeholder="Например: аккумуляторная газонокосилка")

with col2:
    uploaded_image = st.file_uploader("Или загрузите фото", type=["jpg", "jpeg", "png"])

if st.button("Найти товары", type="primary", use_container_width=True):

    # Текст строго обязателен
    if not text_query:
        st.error("Пожалуйста, введите текстовый запрос. Вы также можете прикрепить фото для уточнения поиска.")
    else:
        img_query = None
        if uploaded_image:
            img_query = Image.open(uploaded_image).convert("RGB")
            st.image(img_query, caption="Ваше фото", width=200)

        filters = {}
        if selected_dept != "Все отделы":
            filters["department"] = selected_dept

        with st.spinner("Ищем лучшие совпадения в базе..."):
            # Вызываем функцию напрямую из search_engine.py
            raw_results = smart_search(
                query_text=text_query if text_query else None,
                image=img_query,
                filters=filters if filters else None,
                top_k=6
            )

            st.subheader("Результаты поиска:")

            # Извлекаем метаданные из ответа ChromaDB
            if raw_results and raw_results.get('metadatas') and raw_results['metadatas'][0]:
                cols = st.columns(3)
                for i, item in enumerate(raw_results['metadatas'][0]):
                    with cols[i % 3]:
                        st.image(item.get('image_url', ''), use_container_width=True)
                        st.markdown(f"**{item.get('name', 'Без названия')}**")
                        st.markdown(f"**Цена:** {item.get('price', 0)} ₽")
                        st.caption(f"📁 Отдел: {item.get('department', 'Неизвестно')}")
                        st.markdown(f"[Ссылка на товар]({item.get('url', '#')})")
                        st.divider()
            else:
                st.warning("К сожалению, по вашему запросу ничего не найдено. Попробуйте изменить параметры или выбрать 'Все отделы'.")