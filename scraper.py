import asyncio
import base64
import random
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import easyocr
import cv2

URL = "https://www.avito.ru/moskva/mototsikly_i_mototehnika/kvadrotsikly"

MAX_CLICKS_PER_IP = 2


# ===================== OCR =====================

async def extract_phone_from_image(reader, filename):
    try:
        img = cv2.imread(filename, cv2.IMREAD_UNCHANGED)

        if img is None:
            return None

        if len(img.shape) == 3 and img.shape[2] == 4:
            trans_mask = img[:, :, 3] == 0
            img[trans_mask] = [255, 255, 255, 255]
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        result = reader.readtext(img)

        if result:
            return result[0][1]

        return None

    except Exception as e:
        print(f"OCR ошибка: {e}")
        return None

# ===================== КАПЧА / БЛОК =====================

async def is_blocked(page):
    try:
        title = await page.title()
        url = page.url

        return (
            "Доступ ограничен" in title
            or "blocked" in url
        )
    except:
        return True


async def wait_until_unblocked(page):
    print("КАПЧА/БЛОК — реши вручную")

    while True:
        try:
            await asyncio.sleep(2)

            if not await is_blocked(page):
                print("Капча решена")

                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)

                return

            print("Ждём решения капчи...")

        except:
            print("Страница перезагрузилась, ждём...")
            await asyncio.sleep(2)


# ===================== ОСНОВНЫЕ ОЖИДАНИЯ =====================

async def wait_for_items(page, timeout=60):
    for i in range(timeout):
        try:
            if await is_blocked(page):
                await wait_until_unblocked(page)
                continue

            items = await page.query_selector_all('[data-marker="item"]')

            if items:
                print(f"items появились через {i} сек")
                return items

            print(f"Ждём items... {i}")
            await asyncio.sleep(1)

        except Exception as e:
            print(f"Wait_for_items ошибка: {e}")
            await asyncio.sleep(2)

    return []


async def wait_for_phone_button(item, retries=5, delay=2):
    for i in range(retries):
        try:
            btn = await item.query_selector('button[data-marker^="item-phone-button"]')

            if btn:
                print(f"Кнопка появилась (попытка {i+1})")
                return btn

            print(f"Ждём кнопку... попытка {i+1}")
            await asyncio.sleep(delay)

        except:
            await asyncio.sleep(delay)

    return None


async def safe_click(btn):
    for i in range(3):
        try:
            await btn.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await btn.click()
            return True
        except:
            print(f"Retry click {i+1}")
            await asyncio.sleep(2)

    return False


async def wait_for_new_phone_image(page, existing_count, retries=5, delay=2):
    for i in range(retries):
        try:
            imgs = await page.query_selector_all('img[data-marker="phone-image"]')

            if len(imgs) > existing_count:
                print("Новая картинка")
                return imgs[-1]

            print(f"Ждём новую картинку... {i+1}")
            await asyncio.sleep(delay)

        except Exception as e:
            print(f"Ошибка ожидания картинки: {e}")
            await asyncio.sleep(delay)

    return None


# ===================== MAIN =====================

async def main():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    ]

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=False)
        
        print("Инициализация OCR...")
        reader = easyocr.Reader(["en"])

        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={"width": 1280, "height": 800},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            geolocation={"latitude": 55.75, "longitude": 37.61},
            permissions=["geolocation"],
            java_script_enabled=True
        )

        page = await context.new_page()

        print("Открываем категорию...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=90000)

        # 👇 фикс: если сразу блок
        if await is_blocked(page):
            await wait_until_unblocked(page)
            await page.goto(URL, wait_until="domcontentloaded")

        await page.wait_for_selector("body")
        await asyncio.sleep(3)

        print("Title:", await page.title())

        items = await wait_for_items(page, timeout=60)

        print(f"Найдено объявлений: {len(items)}")

        results = []
        clicks = 0

        for i, item in enumerate(items):
            if clicks >= MAX_CLICKS_PER_IP:
                print("Достигли лимита кликов на IP")
                break

            try:
                # 👇 если внезапно капча в процессе
                if await is_blocked(page):
                    await wait_until_unblocked(page)
                    await page.goto(URL, wait_until="domcontentloaded")
                    items = await wait_for_items(page)
                    continue

                title_el = await item.query_selector('[data-marker="item-title"]')
                title = await title_el.inner_text() if title_el else "no title"

                print(f"\n[{i}] {title}")

                btn = await wait_for_phone_button(item, retries=6, delay=2)

                if not btn:
                    print("Кнопка так и не появилась")
                    continue

                # поведение
                await page.mouse.move(
                    random.randint(200, 800),
                    random.randint(200, 800)
                )
                await asyncio.sleep(random.uniform(0.5, 1.2))

                await btn.hover()
                await asyncio.sleep(random.uniform(0.3, 0.8))

                # считаем ДО клика
                existing_imgs = await page.query_selector_all('img[data-marker="phone-image"]')
                existing_count = len(existing_imgs)

                clicked = await safe_click(btn)

                if not clicked:
                    continue

                await asyncio.sleep(1)

                img = await wait_for_new_phone_image(page, existing_count)

                if not img:
                    print("Картинка не появилась")
                    continue

                src = await img.get_attribute("src")

                filename = None

                if src and src.startswith("data:image"):
                    base64_data = src.split(",")[1]
                    image_bytes = base64.b64decode(base64_data)

                    filename = f"phone_{i}.png"
                    with open(filename, "wb") as f:
                        f.write(image_bytes)

                    print(f"Телефон сохранён: {filename}")

                    phone_text = await extract_phone_from_image(reader, filename)

                    if phone_text:
                        print(f"OCR: {phone_text}")

                        with open("phones.txt", "a", encoding="utf-8") as f:
                            f.write(f"{title} - {phone_text}\n")
                    else:
                        print("OCR не нашёл номер")
                else:
                    print("Телефон не base64")

                results.append({
                    "title": title,
                    "phone_image": filename,
                    "timestamp": datetime.utcnow().isoformat()
                })

                clicks += 1

                await asyncio.sleep(random.uniform(3, 6))

            except Exception as e:
                print(f"Ошибка: {e}")
                await asyncio.sleep(2)

        print("\nРабота завершена, браузер оставлен открытым")

        while True:
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())