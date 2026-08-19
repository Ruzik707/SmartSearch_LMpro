from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
import time
from pathlib import Path


# Функция для сохранения ссылок "на лету"
def save_terminal_url(url, output):
    try:
        with open(output, "a", encoding="utf-8") as f:
            f.write(url + "\n")
    except Exception as e:
        print(f"❌ Ошибка записи в файл: {e}")


def extract_urls(page, url, visited=None, start_url=None):
    if visited is None:
        visited = set()

    if url in visited:
        return

    visited.add(url)
    print(f"🔄 Копаем: {url}")

    # Бронебойный блок загрузки страницы
    try:
        # Даем процессору немного остыть между переходами
        time.sleep(1)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"❌ Ошибка загрузки (пропускаем и идем дальше) {url}: {e}")
        return

    main_area = page.locator('main')

    # Безопасное извлечение текста
    try:
        page_text = main_area.inner_text()
    except Exception:
        page_text = ""

    # ПРАВИЛО 1: Ищем точный текст боковых фильтров
    is_bottom = "Способ получения" in page_text or "Наличие в магазинах" in page_text

    if is_bottom and url != start_url:
        print(f"✅ НАШЛИ ДНО: {url}")
        save_terminal_url(url)  # Сразу пишем в файл на жесткий диск
        return

    # ПРАВИЛО 2: Если фильтров нет, ищем блок с плитками всех возможных видов
    categories_block = main_area.locator(
        '[data-qa="catalogue-categories"], '
        '[data-qa="category-container"], '
        '[data-qa="category-item"], '
        '[data-qa^="catalogue-category-item-"]'
    )
    urls_to_visit = []

    try:
        if categories_block.count() > 0:
            links = categories_block.locator('a[href]').all()
            for link in links:
                href = link.get_attribute('href')
                if href and href.startswith("/catalogue/"):
                    full_url = urljoin("https://lemanapro.ru", href)
                    full_url = full_url.split('?')[0]

                    if full_url not in urls_to_visit and full_url not in visited:
                        urls_to_visit.append(full_url)
    except Exception as e:
        print(f"⚠️ Ошибка при поиске подкатегорий: {e}")

    if urls_to_visit:
        print(f"📂 Нашли {len(urls_to_visit)} подкатегорий. Идем вглубь...")
        for next_url in urls_to_visit:
            extract_urls(page, next_url, visited, start_url)
    else:
        # Резервный выход
        print(f"✅ НАШЛИ ДНО (тупик): {url}")
        save_terminal_url(url)


if __name__ == "__main__":
    # Список всех главных отделов Лемана ПРО
    root_categories = [
        "https://lemanapro.ru/catalogue/sad/",
        "https://lemanapro.ru/catalogue/klimaticheskaya-tehnika-i-ventilyaciya/",
        "https://lemanapro.ru/catalogue/dekor/",
        "https://lemanapro.ru/catalogue/tekstil/",
        "https://lemanapro.ru/catalogue/santehnika/",
        "https://lemanapro.ru/catalogue/kraski/",
        "https://lemanapro.ru/catalogue/dveri/",
        "https://lemanapro.ru/catalogue/plitka/",
        "https://lemanapro.ru/catalogue/napolnye-pokrytiya/",
        "https://lemanapro.ru/catalogue/instrumenty/,"
        "https://lemanapro.ru/catalogue/vodosnabzhenie/",
        "https://lemanapro.ru/catalogue/stroymaterialy/",
        "https://lemanapro.ru/catalogue/elektrotovary/",
        "https://lemanapro.ru/catalogue/osveshchenie/",
        "https://lemanapro.ru/catalogue/stolyarnye-izdeliya/",
        "https://lemanapro.ru/catalogue/skobyanye-izdeliya/",
        "https://lemanapro.ru/catalogue/okna/",
        "https://lemanapro.ru/catalogue/kuhni/",
        "https://lemanapro.ru/catalogue/bytovaya-tehnika/",
        "https://lemanapro.ru/catalogue/mebel-dlya-doma/",
        "https://lemanapro.ru/catalogue/hranenie/",
        "https://lemanapro.ru/catalogue/otopitelnoe-oborudovanie/",
        "https://lemanapro.ru/catalogue/specodezhda-i-sredstva-zashchity/",
        "https://lemanapro.ru/catalogue/tovary-dlya-uborki/"
    ]

    output = Path(__file__).parent.parent.parent / "data" / "terminal_categories.txt"

    # Перед началом очищаем файл от старых запусков
    with open(output, "w", encoding="utf-8") as f:
        f.write("")

    # Общее множество посещенных ссылок, чтобы не ходить по одним и тем же
    # подкатегориям, если они пересекаются в разных отделах
    global_visited = set()

    with sync_playwright() as p:
        print("🔗 Подключаемся к живому браузеру...")
        try:
            st = time.time()
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.new_page()

            # Проходимся по каждому отделу по очереди
            for start_url in root_categories:
                print(f"\n=======================================================")
                print(f"🚀 НАЧИНАЕМ СБОР ОТДЕЛА: {start_url}")
                print(f"=======================================================\n")

                # Запускаем рекурсию для конкретного отдела
                extract_urls(page, start_url, visited=global_visited, start_url=start_url)

            end = time.time()
            t = (end - st) / 60 / 60
            print(f"\n🎉 Ночной сбор всех отделов успешно завершен!\nСбор работал {t:.2f} часов.")
            page.close()

        except Exception as e:
            print(f"❌ Фатальная ошибка подключения: {e}")