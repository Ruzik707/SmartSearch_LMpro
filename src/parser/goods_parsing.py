import json
import time
import re
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from pathlib import Path

input = Path(__file__).parent.parent.parent / "data" / "terminal_categories.txt"
output = Path(__file__).parent.parent.parent / "data" / "lem_products.jsonl"

DEPARTMENT_MAP = {
    "Декор": "Декор",
    "Мебель": "Кухни",
    "Хранение": "Хранение",
    "Сантехника": "Сантехника",
    "Отопительное оборудование": "Водоснабжение",
    "Климат и вентиляция": "Водоснабжение",
    "Инструменты": "Инструменты",
    "Электротовары": "Электротовары",
    "Плитка": "Плитка",
    "Краски": "Краски",
    "Кухни": "Кухни",
    "Водоснабжение": "Водоснабжение",
    "Бытовая техника": "Кухни",
    "Напольные покрытия": "Напольные покрытия",
    "Освещение": "Освещение",
    "Текстиль": "Декор",
    "Столярные изделия": "Столярные изделия",
    "Скобяные изделия": "Скобяные изделия",
    "Окна": "Столярные изделия",
    "Двери": "Столярные изделия",
    "Стройматериалы": "Стройматериалы",
    "Сад": "Сад",
    "Спецодежда и средства защиты": "Инструменты",
    "Товары для уборки": "Сад"
}


def scrape_page_products(page, url):
    """Собирает до 60 товаров с переданной страницы каталога."""
    products_data = []

    print(f"🔄 Парсим товары: {url}")
    try:
        time.sleep(1)  # Даем ноуту подышать
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)  # Ждем прогрузки React-компонентов

        try:
            page.wait_for_selector('[data-testid="breadcrumbItemName"]', timeout=5000)
            breadcrumbs = page.locator('[data-testid="breadcrumbItemName"]').all_inner_texts()
            raw_department = breadcrumbs[2].strip() if len(breadcrumbs) >= 3 else "Разное"
        except Exception as e:
            raw_department = "Разное"

        strict_department = DEPARTMENT_MAP.get(raw_department, raw_department)
        print(f"📁 Отдел: {strict_department}")

    except Exception as e:
        print(f"❌ Ошибка загрузки страницы {url}: {e}")
        return products_data

    # Ищем все карточки товаров на странице
    product_cards = page.locator('[data-qa="product"]').all()

    for card in product_cards:
        try:
            # 1. Название и Ссылка
            link_locator = card.locator('a[data-qa="product-name"]').first
            if link_locator.count() > 0:
                name = link_locator.inner_text().strip()
                href = link_locator.get_attribute('href')
                prod_url = urljoin("https://lemanapro.ru", href) if href else ""
            else:
                continue  # Пропускаем битые карточки

            # 2. Актуальная цена (всегда лежит в price-block-price, со скидкой или без)
            price_locator = card.locator('[data-testid="price-block-price"]').first
            if price_locator.count() > 0:
                raw_price = price_locator.inner_text()
                price = re.sub(r'[^\d]', '', raw_price)
            else:
                price = "0"

            # 3. Картинка (вытаскиваем высокое разрешение)
            img_locator = card.locator('img').first
            img_url = ""
            if img_locator.count() > 0:
                src = img_locator.get_attribute('data-src') or img_locator.get_attribute('src')
                if src:
                    # Повышаем качество фото с 128/240 до 600px
                    img_url = re.sub(r'w_\d+/h_\d+', 'w_600/h_600', src)

            # Сохраняем карточку
            if name and prod_url and img_url:
                products_data.append({
                    "name": name,
                    "price": price,
                    "url": prod_url,
                    "image_url": img_url,
                    "department": strict_department
                })
        except Exception:
            pass  # Игнорируем ошибки в отдельных карточках

    print(f"✅ Собрано товаров: {len(products_data)}")
    return products_data


if __name__ == "__main__":
    # Читаем собранные ссылки
    try:
        with open(input, "r", encoding="utf-8") as f:
            category_urls = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("❌ Файл terminal_categories.txt не найден!")
        exit()

    print(f"📦 Загружено категорий для парсинга: {len(category_urls)}")

    with sync_playwright() as p:
        print("🔗 Подключаемся к живому браузеру...")
        try:
            start_time = time.time()
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.new_page()

            # Открываем файл для дозаписи товаров (JSONL формат)
            with open(output, "a", encoding="utf-8") as file_out:
                for idx, url in enumerate(category_urls, 1):
                    print(f"\n--- Категория {idx} из {len(category_urls)} ---")

                    products = scrape_page_products(page, url)

                    # Сразу пишем собранные товары на диск
                    for item in products:
                        file_out.write(json.dumps(item, ensure_ascii=False) + "\n")

            elapsed = (time.time() - start_time) / 3600
            print(f"\n🎉 Сбор товаров завершен! Время работы: {elapsed:.2f} часов.")
            page.close()

        except Exception as e:
            print(f"❌ Фатальная ошибка: {e}")