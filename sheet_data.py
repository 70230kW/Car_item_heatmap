"""Convert explicitly mapped spreadsheet columns to the inventory schema."""
import math
import re
import unicodedata
from datetime import date

from scraper import detect_body, detect_maker, detect_year


def clean(value):
    return unicodedata.normalize("NFKC", ("" if value is None else str(value))).strip()


def number(value, unit, mileage=False):
    text = clean(value).replace(" ", "")
    if mileage:
        match = re.fullmatch(r"([0-9][0-9,]*(?:\.[0-9]+)?)(万|千)?(km|キロ)?", text, re.I)
        if not match:
            return None
        scale = 10000 if match[2] == "万" else 1000 if match[2] == "千" else 1 if match[3] else (10000 if unit == "man_km" else 1)
    else:
        match = re.fullmatch(r"[¥￥]?([0-9][0-9,]*(?:\.[0-9]+)?)(万円|万|円)?", text)
        if not match:
            return None
        suffix = match[2]
        scale = 1 if suffix in ("万円", "万") else .0001 if suffix == "円" or text.startswith(("¥", "￥")) or unit == "yen" else 1
    result = float(match[1].replace(",", "")) * scale
    return result if math.isfinite(result) else None


def convert_rows(headers, rows, mapping, default_company, price_unit, mileage_unit, source):
    if "price" not in mapping:
        raise ValueError("価格の列を選択してください。")
    if "year" not in mapping and "mileage" not in mapping:
        raise ValueError("年式または走行距離の列を選択してください。")
    for index in mapping.values():
        if not isinstance(index, int) or index < 0 or index >= len(headers):
            raise ValueError("列の指定が不正です。プレビューを読み直してください。")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("同じ列を複数の項目に指定しないでください。")
    groups = {}
    skipped = 0
    for row_no, row in enumerate(rows, 1):
        def cell(key):
            index = mapping.get(key)
            return row[index] if index is not None and index < len(row) else ""
        price = number(cell("price"), price_unit)
        if price is None or not 0 < price <= 100000:
            skipped += 1
            continue
        company = clean(cell("company")) or default_company.strip()
        if not company:
            raise ValueError("店舗名を入力するか、会社名の列を選択してください。")
        year_text = clean(cell("year"))
        match = re.fullmatch(r"(\d{4})(?:\.0)?(?:年)?", year_text)
        year = int(match[1]) if match else detect_year("年式 " + year_text)
        if year is not None and not 1886 <= year <= date.today().year + 2:
            year = None
        km = number(cell("mileage"), mileage_unit, mileage=True)
        mileage = int(round(km)) if km is not None and 0 <= km <= 10000000 else None
        title = clean(cell("name")) or "シートの車両 " + str(row_no)
        vehicle = {"id": source + ":" + str(row_no), "price": round(price, 4), "year": year,
                   "mileage": mileage, "text": title[:200], "maker": detect_maker(title), "body": detect_body(title)}
        groups.setdefault(company, []).append(vehicle)
    if not groups:
        raise ValueError("有効な価格を持つ車両がありません。価格の列と単位を確認してください。")
    stores = []
    for name, vehicles in groups.items():
        warnings = []
        missing_year = sum(v["year"] is None for v in vehicles)
        missing_km = sum(v["mileage"] is None for v in vehicles)
        if missing_year:
            warnings.append(str(missing_year) + "台は年式が不明です。")
        if missing_km:
            warnings.append(str(missing_km) + "台は走行距離が不明です。")
        stores.append({"name": name, "data": {"vehicles": vehicles, "pages": 1, "warnings": warnings}})
    return {"stores": stores, "rows_read": len(rows), "skipped_rows": skipped}
