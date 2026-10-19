import os
import re
import time
import hashlib
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin


BASE_URL = "https://www.aogaku-rugby.com/"
SOURCE_URL = "https://www.aogaku-rugby.com/topics_list/"
OUTPUT_FILE = "aogaku_rugby.xml"

FEED_TITLE = "青山学院大学ラグビー部 トピックス"
FEED_LINK = SOURCE_URL
FEED_DESCRIPTION = (
    "青山学院大学ラグビー部公式サイト "
    "トピックス更新情報"
)

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

DATE_RE = re.compile(
    r"(20\d{2})/(\d{1,2})/(\d{1,2})"
)


def fetch(url, params=None):
    last_error = None

    for attempt in range(1, 4):
        try:
            print(
                f"取得試行 {attempt}/3: {url}"
            )

            response = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=30
            )

            print(
                f"HTTP: {response.status_code} / "
                f"取得バイト数: {len(response.content)} / "
                f"最終URL: {response.url}"
            )

            response.raise_for_status()
            response.encoding = "utf-8"

            return response.text

        except Exception as e:
            last_error = e

            print(
                f"取得失敗: {e}"
            )

            if attempt < 3:
                print(
                    "10秒待って再試行します。"
                )
                time.sleep(10)

    raise RuntimeError(
        "ページを取得できませんでした: "
        f"{url} / {last_error}"
    )


def clean_text(text):
    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def make_guid(link):
    return hashlib.sha256(
        link.encode("utf-8")
    ).hexdigest()


def extract_articles(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    articles = []
    seen_links = set()

    for a in soup.find_all(
        "a",
        href=True
    ):
        href = a.get(
            "href",
            ""
        )

        if "topics_detail/id=" not in href:
            continue

        text = clean_text(
            a.get_text(
                " ",
                strip=True
            )
        )

        date_match = DATE_RE.search(
            text
        )

        if not date_match:
            continue

        try:
            published = datetime(
                int(date_match.group(1)),
                int(date_match.group(2)),
                int(date_match.group(3)),
                12,
                0,
                0,
                tzinfo=JST
            )

        except ValueError:
            continue

        link = urljoin(
            BASE_URL,
            href
        )

        if link in seen_links:
            continue

        seen_links.add(link)

        text_without_date = DATE_RE.sub(
            "",
            text
        )

        text_without_date = clean_text(
            text_without_date
        )

        category = ""

        known_categories = [
            "お知らせ",
            "ラストメッセージ",
            "菅平日記",
            "試合情報",
            "イベント",
        ]

        title = text_without_date

        for candidate in known_categories:
            if text_without_date.startswith(
                candidate
            ):
                category = candidate

                title = clean_text(
                    text_without_date[
                        len(candidate):
                    ]
                )

                break

        if not title:
            continue

        description = (
            f"[{category}] {title}"
            if category
            else title
        )

        articles.append({
            "title": title,
            "link": link,
            "guid": make_guid(link),
            "published": published,
            "description": description,
            "category": category,
        })

    articles.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    return articles


def load_existing():
    existing = {}

    if not os.path.exists(
        OUTPUT_FILE
    ):
        return existing

    tree = ET.parse(
        OUTPUT_FILE
    )

    root = tree.getroot()

    for item in root.findall(
        "./channel/item"
    ):
        title = item.findtext(
            "title",
            ""
        ).strip()

        link = item.findtext(
            "link",
            ""
        ).strip()

        guid = item.findtext(
            "guid",
            ""
        ).strip()

        pub_date = item.findtext(
            "pubDate",
            ""
        ).strip()

        description = item.findtext(
            "description",
            ""
        ).strip()

        category = item.findtext(
            "category",
            ""
        ).strip()

        if not link or not title:
            continue

        try:
            published = parsedate_to_datetime(
                pub_date
            )

            if published.tzinfo is None:
                published = published.replace(
                    tzinfo=JST
                )

        except Exception:
            continue

        existing[link] = {
            "title": title,
            "link": link,
            "guid": (
                guid
                or make_guid(link)
            ),
            "published": published,
            "description": description,
            "category": category,
        }

    return existing


def build_rss(articles):
    rss = ET.Element(
        "rss",
        version="2.0"
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = FEED_TITLE

    ET.SubElement(
        channel,
        "link"
    ).text = FEED_LINK

    ET.SubElement(
        channel,
        "description"
    ).text = FEED_DESCRIPTION

    ET.SubElement(
        channel,
        "language"
    ).text = "ja"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = format_datetime(
        datetime.now(JST)
    )

    for article in articles:
        item = ET.SubElement(
            channel,
            "item"
        )

        ET.SubElement(
            item,
            "title"
        ).text = article["title"]

        ET.SubElement(
            item,
            "link"
        ).text = article["link"]

        guid = ET.SubElement(
            item,
            "guid"
        )

        guid.set(
            "isPermaLink",
            "false"
        )

        guid.text = article["guid"]

        ET.SubElement(
            item,
            "pubDate"
        ).text = format_datetime(
            article["published"]
        )

        ET.SubElement(
            item,
            "description"
        ).text = article["description"]

        if article.get(
            "category"
        ):
            ET.SubElement(
                item,
                "category"
            ).text = article["category"]

    tree = ET.ElementTree(
        rss
    )

    try:
        ET.indent(
            tree,
            space="  "
        )
    except AttributeError:
        pass

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )


def main():
    print(
        "=" * 70
    )
    print(
        "青山学院大学ラグビー部 "
        "トピックス RSS"
    )
    print(
        "=" * 70
    )

    existing = load_existing()

    print(
        f"既存RSS件数: {len(existing)}"
    )

    try:
        current_year = datetime.now(
            JST
        ).year

        html = fetch(
            SOURCE_URL,
            params={
                "season": str(
                    current_year
                )
            }
        )

        current = extract_articles(
            html
        )

        print()
        print(
            f"{current_year}年度 "
            f"取得件数: {len(current)}件"
        )

        if not current:
            raise RuntimeError(
                "トピックスを"
                "1件も抽出できませんでした。"
            )

        current_by_link = {
            article["link"]: article
            for article in current
        }

        new_count = sum(
            1
            for link in current_by_link
            if link not in existing
        )

        merged = dict(
            existing
        )

        merged.update(
            current_by_link
        )

        all_articles = list(
            merged.values()
        )

        all_articles.sort(
            key=lambda x: x["published"],
            reverse=True
        )

        print(
            f"新規記事: {new_count}件"
        )

        print(
            f"累積RSS件数: "
            f"{len(all_articles)}件"
        )

        print()
        print("最新30件:")

        for article in all_articles[:30]:
            category = (
                f"[{article['category']}] "
                if article.get("category")
                else ""
            )

            print(
                article["published"]
                .astimezone(JST)
                .strftime("%Y-%m-%d"),
                category
                + article["title"]
            )

        build_rss(
            all_articles
        )

        print()
        print(
            f"保存完了: "
            f"{OUTPUT_FILE} "
            f"({len(all_articles)}件)"
        )

    except Exception:
        print()
        print(
            "取得・解析に失敗したため、"
            "既存RSSは変更しません。"
        )
        raise


if __name__ == "__main__":
    main()