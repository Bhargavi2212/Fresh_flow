"""Seed ~600 products with 2+ aliases each including slang. Realistic pricing."""
import asyncio
import random
from decimal import Decimal

from backend.services.database import execute, get_pool


def _pick(supplier_ids: list[str]) -> str:
    return random.choice(supplier_ids)


# (name, aliases, uom, case_size, unit_price, cost_price, shelf_days, storage)
# Category/subcategory set per block. Aliases must include slang.
FRESH_FISH: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("King Salmon Fillet 10lb Case", ["king salmon", "chinook", "chinook salmon", "spring salmon", "king"], "case", 10, 72, 58, 5, "refrigerated"),
    ("Atlantic Salmon Fillet 10lb Case", ["atlantic salmon", "salmon fillet", "farmed salmon"], "case", 10, 65, 52, 5, "refrigerated"),
    ("Sockeye Salmon Whole 10lb Case", ["sockeye", "red salmon", "sockeye salmon"], "case", 10, 85, 68, 5, "refrigerated"),
    ("Coho Salmon Fillet 8lb Case", ["coho", "silver salmon", "coho salmon"], "case", 8, 70, 56, 5, "refrigerated"),
    ("Halibut Fillet 10lb Case", ["halibut", "halibut fillet", "white halibut"], "case", 10, 95, 76, 4, "refrigerated"),
    ("Pacific Cod Fillet 10lb Case", ["cod", "pacific cod", "cod fillet"], "case", 10, 45, 36, 4, "refrigerated"),
    ("Dover Sole Whole 5lb Case", ["dover sole", "sole", "gray sole"], "case", 5, 55, 44, 3, "refrigerated"),
    ("Branzino Whole 1.5lb Each", ["branzino", "european sea bass", "loup de mer"], "each", 1.5, 12, 9.5, 3, "refrigerated"),
    ("Red Snapper Whole 5lb Case", ["red snapper", "snapper", "american red snapper"], "case", 5, 65, 52, 3, "refrigerated"),
    ("Swordfish Steak 10lb Case", ["swordfish", "swordfish steak"], "case", 10, 88, 70, 3, "refrigerated"),
    ("Yellowfin Tuna Steak 10lb Case", ["yellowfin", "ahi tuna", "tuna steak"], "case", 10, 95, 76, 3, "refrigerated"),
    ("Mahi Mahi Fillet 10lb Case", ["mahi mahi", "dorado", "dolphinfish"], "case", 10, 75, 60, 4, "refrigerated"),
    ("Sea Bass Fillet 5lb Case", ["sea bass", "chilean sea bass", "patagonian toothfish"], "case", 5, 85, 68, 4, "refrigerated"),
    ("Tilapia Fillet 10lb Case", ["tilapia", "tilapia fillet"], "case", 10, 28, 22, 4, "refrigerated"),
    ("Rainbow Trout Whole 5lb Case", ["rainbow trout", "trout", "whole trout"], "case", 5, 45, 36, 4, "refrigerated"),
    ("Flounder Fillet 5lb Case", ["flounder", "flounder fillet", "summer flounder"], "case", 5, 38, 30, 3, "refrigerated"),
    ("Monkfish Tail 5lb Case", ["monkfish", "monkfish tail", "poor man's lobster"], "case", 5, 55, 44, 3, "refrigerated"),
    ("Grouper Fillet 10lb Case", ["grouper", "grouper fillet", "red grouper"], "case", 10, 78, 62, 3, "refrigerated"),
    ("Lingcod Fillet 10lb Case", ["lingcod", "ling cod", "greenling"], "case", 10, 48, 38, 4, "refrigerated"),
    ("Rockfish Fillet 10lb Case", ["rockfish", "pacific rockfish", "snapper"], "case", 10, 42, 34, 4, "refrigerated"),
]
SHELLFISH: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("Jumbo Shrimp 16/20 5lb Case", ["jumbos", "jumbo shrimp", "16/20 shrimp", "large shrimp"], "case", 5, 68, 54, 3, "refrigerated"),
    ("Jumbo Shrimp 21/25 5lb Case", ["21/25 shrimp", "extra large shrimp", "shrimp 21/25"], "case", 5, 55, 44, 3, "refrigerated"),
    ("Jumbo Shrimp 26/30 5lb Case", ["26/30 shrimp", "large shrimp", "shrimp 26/30"], "case", 5, 48, 38, 3, "refrigerated"),
    ("Live Maine Lobster 1.5lb Each", ["maine lobster", "lobster", "live lobster"], "each", 1.5, 28, 22, 2, "refrigerated"),
    ("Lobster Tail 6oz Each", ["lobster tail", "lobster tails"], "each", 0.375, 18, 14, 3, "refrigerated"),
    ("Dungeness Crab Whole 2lb Each", ["dungeness crab", "dungeness", "crab"], "each", 2, 22, 18, 2, "refrigerated"),
    ("Snow Crab Clusters 10lb Case", ["snow crab", "snow crab clusters", "crab clusters"], "case", 10, 95, 76, 3, "refrigerated"),
    ("Sea Scallops U10 5lb Case", ["sea scallops", "scallops", "u10 scallops"], "case", 5, 72, 58, 3, "refrigerated"),
    ("Bay Scallops 5lb Case", ["bay scallops", "small scallops"], "case", 5, 42, 34, 3, "refrigerated"),
    ("Live Oysters Dozen", ["oysters", "live oysters", "dozen oysters"], "dozen", 12, 24, 19, 5, "refrigerated"),
    ("Littleneck Clams 50ct Bag", ["littleneck clams", "clams", "little necks"], "case", 50, 45, 36, 3, "refrigerated"),
    ("Mussels 5lb Bag", ["mussels", "fresh mussels", "blue mussels"], "case", 5, 22, 18, 3, "refrigerated"),
    ("Soft-Shell Crab 12ct Case", ["soft shell crab", "soft shells", "softshell"], "case", 12, 65, 52, 1, "refrigerated"),
]
FROZEN_FISH: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("Frozen Salmon Fillet 10lb Case", ["frozen salmon", "frozen king salmon"], "case", 10, 58, 46, 180, "frozen"),
    ("Frozen Cod Fillet 10lb Case", ["frozen cod", "frozen cod fillet"], "case", 10, 38, 30, 180, "frozen"),
    ("Frozen Shrimp 16/20 5lb Case", ["frozen shrimp", "frozen jumbos"], "case", 5, 52, 42, 180, "frozen"),
    ("Frozen Scallops 5lb Case", ["frozen scallops", "frozen sea scallops"], "case", 5, 62, 50, 180, "frozen"),
    ("Frozen Halibut 10lb Case", ["frozen halibut", "frozen halibut fillet"], "case", 10, 78, 62, 180, "frozen"),
    ("Frozen Mahi Mahi 10lb Case", ["frozen mahi", "frozen mahi mahi"], "case", 10, 62, 50, 180, "frozen"),
    ("Frozen Tilapia 10lb Case", ["frozen tilapia", "frozen tilapia fillet"], "case", 10, 24, 19, 180, "frozen"),
    ("Frozen Tuna Steak 10lb Case", ["frozen tuna", "frozen ahi"], "case", 10, 82, 66, 180, "frozen"),
    ("Frozen Lobster Tail 4oz", ["frozen lobster tail", "frozen lobster"], "each", 0.25, 14, 11, 365, "frozen"),
    ("Frozen Crab Meat 1lb", ["frozen crab meat", "crab meat"], "lb", 1, 28, 22, 180, "frozen"),
]
FRUITS: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("Strawberries Flat 12lb", ["strawberries", "strawberry", "berries", "fresh strawberries"], "flat", 12, 22, 18, 5, "refrigerated"),
    ("Blueberries Flat 12ct", ["blueberries", "blueberry", "berries", "fresh blueberries"], "flat", 12, 42, 34, 5, "refrigerated"),
    ("Raspberries Half Flat", ["raspberries", "raspberry", "berries", "fresh raspberries"], "flat", 6, 28, 22, 3, "refrigerated"),
    ("Blackberries Flat", ["blackberries", "blackberry", "berries"], "flat", 12, 38, 30, 4, "refrigerated"),
    ("Lemons Case 165ct", ["lemons", "lemon", "fresh lemons"], "case", 165, 48, 38, 14, "refrigerated"),
    ("Limes Case 200ct", ["limes", "lime", "fresh limes"], "case", 200, 42, 34, 14, "refrigerated"),
    ("Avocados Case 48ct", ["avocados", "avocado", "avos"], "case", 48, 52, 42, 7, "refrigerated"),
    ("Mangoes Case 12ct", ["mangoes", "mango", "fresh mango"], "case", 12, 38, 30, 7, "refrigerated"),
    ("Pineapple Case 8ct", ["pineapple", "pineapples", "fresh pineapple"], "case", 8, 45, 36, 7, "ambient"),
    ("Watermelon Each", ["watermelon", "watermelons", "melon"], "each", 1, 18, 14, 7, "ambient"),
    ("Cantaloupe Case 9ct", ["cantaloupe", "cantaloupes", "melon"], "case", 9, 32, 26, 7, "refrigerated"),
    ("Honeydew Case 6ct", ["honeydew", "honeydew melon"], "case", 6, 28, 22, 7, "refrigerated"),
    ("Grapes Red 18lb Case", ["red grapes", "grapes", "table grapes"], "case", 18, 42, 34, 7, "refrigerated"),
    ("Grapes Green 18lb Case", ["green grapes", "grapes", "table grapes"], "case", 18, 42, 34, 7, "refrigerated"),
    ("Peaches Case 48ct", ["peaches", "peach", "stone fruit"], "case", 48, 55, 44, 5, "refrigerated"),
    ("Nectarines Case 48ct", ["nectarines", "nectarine", "stone fruit"], "case", 48, 52, 42, 5, "refrigerated"),
    ("Plums Case 36ct", ["plums", "plum", "stone fruit"], "case", 36, 38, 30, 5, "refrigerated"),
    ("Pears Case 48ct", ["pears", "pear", "anjou pears"], "case", 48, 45, 36, 14, "refrigerated"),
    ("Apples Granny Smith Case", ["granny smith", "green apples", "apples"], "case", 48, 38, 30, 21, "refrigerated"),
    ("Apples Gala Case", ["gala apples", "apples", "gala"], "case", 48, 35, 28, 21, "refrigerated"),
]
VEGETABLES: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("Roma Tomatoes 25lb Case", ["roma tomatoes", "roma", "tomatoes", "plum tomatoes"], "case", 25, 32, 26, 7, "refrigerated"),
    ("Heirloom Tomatoes 10lb Case", ["heirloom tomatoes", "heirloom", "tomatoes"], "case", 10, 55, 44, 5, "refrigerated"),
    ("Mixed Greens 5lb Case", ["mixed greens", "mesclun", "salad mix"], "case", 5, 28, 22, 5, "refrigerated"),
    ("Arugula 5lb Case", ["arugula", "rocket", "rucola"], "case", 5, 42, 34, 4, "refrigerated"),
    ("Spinach 10lb Case", ["spinach", "fresh spinach", "baby spinach"], "case", 10, 28, 22, 5, "refrigerated"),
    ("Kale 10lb Case", ["kale", "curly kale", "fresh kale"], "case", 10, 32, 26, 5, "refrigerated"),
    ("Romaine Lettuce 24ct Case", ["romaine", "romaine lettuce", "cos lettuce"], "case", 24, 35, 28, 7, "refrigerated"),
    ("Bell Peppers Case 24ct", ["bell peppers", "peppers", "sweet peppers"], "case", 24, 42, 34, 7, "refrigerated"),
    ("Yellow Onions 50lb Bag", ["yellow onions", "onions", "cooking onions"], "case", 50, 28, 22, 21, "ambient"),
    ("Red Onions 25lb Case", ["red onions", "onions"], "case", 25, 32, 26, 21, "ambient"),
    ("Cremini Mushrooms 5lb Case", ["cremini", "mushrooms", "baby bella"], "case", 5, 38, 30, 5, "refrigerated"),
    ("Button Mushrooms 10lb Case", ["button mushrooms", "white mushrooms", "mushrooms"], "case", 10, 32, 26, 5, "refrigerated"),
    ("Fresh Basil Bunch", ["basil", "fresh basil", "basil bunch"], "each", 1, 4, 3.2, 5, "refrigerated"),
    ("Fresh Cilantro Bunch", ["cilantro", "fresh cilantro", "coriander"], "each", 1, 3, 2.4, 5, "refrigerated"),
    ("Fresh Parsley Bunch", ["parsley", "fresh parsley", "flat leaf parsley"], "each", 1, 3, 2.4, 5, "refrigerated"),
    ("Fresh Rosemary Bunch", ["rosemary", "fresh rosemary"], "each", 1, 4, 3.2, 7, "refrigerated"),
    ("Fresh Thyme Bunch", ["thyme", "fresh thyme"], "each", 1, 4, 3.2, 7, "refrigerated"),
    ("Carrots 25lb Case", ["carrots", "fresh carrots", "baby carrots"], "case", 25, 22, 18, 14, "refrigerated"),
    ("Celery 30ct Case", ["celery", "celery bunch", "fresh celery"], "case", 30, 28, 22, 14, "refrigerated"),
    ("Broccoli 14ct Case", ["broccoli", "broccoli crowns", "fresh broccoli"], "case", 14, 38, 30, 5, "refrigerated"),
]
DAIRY: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("Heavy Cream Quart", ["heavy cream", "heavy whipping cream", "cream"], "each", 1, 6, 4.8, 21, "refrigerated"),
    ("Heavy Cream Half Gallon", ["heavy cream", "whipping cream"], "each", 1, 10, 8, 21, "refrigerated"),
    ("Butter Salted 1lb", ["butter", "salted butter", "stick butter"], "lb", 1, 5, 4, 60, "refrigerated"),
    ("Butter Unsalted 1lb", ["unsalted butter", "butter"], "lb", 1, 5.5, 4.4, 60, "refrigerated"),
    ("Parmesan Wedge 5lb", ["parmesan", "parm", "parmesan cheese"], "lb", 5, 42, 34, 90, "refrigerated"),
    ("Mozzarella Fresh 1lb", ["mozzarella", "fresh mozzarella", "mozz"], "lb", 1, 8, 6.4, 14, "refrigerated"),
    ("Cheddar Block 5lb", ["cheddar", "cheddar cheese", "sharp cheddar"], "lb", 5, 28, 22, 90, "refrigerated"),
    ("Cream Cheese 3lb Case", ["cream cheese", "philly"], "case", 3, 14, 11, 30, "refrigerated"),
    ("Eggs Dozen", ["eggs", "dozen eggs", "large eggs"], "dozen", 12, 5, 4, 21, "refrigerated"),
    ("Eggs Case 30 Dozen", ["eggs case", "egg case", "bulk eggs"], "case", 360, 120, 96, 21, "refrigerated"),
    ("Whole Milk Gallon", ["whole milk", "milk", "gallon milk"], "each", 1, 4, 3.2, 7, "refrigerated"),
    ("Half and Half Quart", ["half and half", "half & half"], "each", 1, 4.5, 3.6, 14, "refrigerated"),
    ("Plain Yogurt 5lb Tub", ["yogurt", "plain yogurt", "greek yogurt"], "case", 5, 12, 9.6, 21, "refrigerated"),
    ("Sour Cream 5lb Tub", ["sour cream", "sour cream tub"], "case", 5, 14, 11, 21, "refrigerated"),
    ("Ricotta 5lb Tub", ["ricotta", "ricotta cheese", "whole milk ricotta"], "case", 5, 22, 18, 14, "refrigerated"),
]
DRY_GOODS: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("Olive Oil Extra Virgin 1gal", ["olive oil", "evoo", "extra virgin olive oil"], "each", 1, 28, 22, 365, "ambient"),
    ("Vegetable Oil 1gal", ["vegetable oil", "cooking oil", "neutral oil"], "each", 1, 12, 9.6, 365, "ambient"),
    ("Red Wine Vinegar 1gal", ["red wine vinegar", "vinegar", "wine vinegar"], "each", 1, 18, 14, 365, "ambient"),
    ("Balsamic Vinegar 1qt", ["balsamic", "balsamic vinegar", "balsamic glaze"], "each", 1, 22, 18, 365, "ambient"),
    ("All-Purpose Flour 50lb", ["flour", "ap flour", "all purpose flour"], "case", 50, 28, 22, 365, "ambient"),
    ("Granulated Sugar 50lb", ["sugar", "white sugar", "granulated sugar"], "case", 50, 35, 28, 365, "ambient"),
    ("Pasta Spaghetti 20lb Case", ["spaghetti", "pasta", "spaghetti pasta"], "case", 20, 28, 22, 365, "ambient"),
    ("Pasta Penne 20lb Case", ["penne", "pasta", "penne pasta"], "case", 20, 28, 22, 365, "ambient"),
    ("Arborio Rice 25lb Bag", ["arborio rice", "risotto rice", "rice"], "case", 25, 45, 36, 365, "ambient"),
    ("Jasmine Rice 25lb Bag", ["jasmine rice", "rice", "thai rice"], "case", 25, 32, 26, 365, "ambient"),
    ("Canned Tomatoes 6/102oz", ["canned tomatoes", "tomatoes canned", "san marzano"], "case", 6, 28, 22, 365, "ambient"),
    ("Tomato Paste 6/4.5oz", ["tomato paste", "paste", "tomato paste can"], "case", 6, 12, 9.6, 365, "ambient"),
    ("Chicken Stock 6/1qt", ["chicken stock", "stock", "chicken broth"], "case", 6, 18, 14, 365, "ambient"),
    ("Black Peppercorns 1lb", ["black pepper", "peppercorns", "whole pepper"], "lb", 1, 12, 9.6, 365, "ambient"),
    ("Kosher Salt 3lb Box", ["kosher salt", "salt", "coarse salt"], "case", 3, 5, 4, 365, "ambient"),
    ("Paprika 1lb", ["paprika", "hungarian paprika", "spice"], "lb", 1, 14, 11, 365, "ambient"),
    ("Cumin 1lb", ["cumin", "ground cumin", "spice"], "lb", 1, 12, 9.6, 365, "ambient"),
    ("Oregano 1lb", ["oregano", "dried oregano", "spice"], "lb", 1, 14, 11, 365, "ambient"),
    ("Garlic Powder 1lb", ["garlic powder", "garlic", "spice"], "lb", 1, 10, 8, 365, "ambient"),
    ("Onion Powder 1lb", ["onion powder", "onion", "spice"], "lb", 1, 10, 8, 365, "ambient"),
]
PAPER: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("To-Go Containers 9x9 500ct", ["to go containers", "takeout containers", "clamshells"], "case", 500, 28, 22, 365, "ambient"),
    ("Foam Clamshells 500ct", ["foam clamshells", "styrofoam", "to go"], "case", 500, 22, 18, 365, "ambient"),
    ("Paper Napkins 500ct", ["paper napkins", "napkins", "dinner napkins"], "case", 500, 18, 14, 365, "ambient"),
    ("Paper Towels 12 Roll", ["paper towels", "towels", "kitchen towels"], "case", 12, 28, 22, 365, "ambient"),
    ("Disposable Gloves 100ct", ["gloves", "disposable gloves", "food service gloves"], "case", 100, 12, 9.6, 365, "ambient"),
    ("Plastic Wrap 18in 2000ft", ["plastic wrap", "saran wrap", "cling film"], "each", 1, 28, 22, 365, "ambient"),
    ("Aluminum Foil 18in 500ft", ["aluminum foil", "foil", "tin foil"], "each", 1, 32, 26, 365, "ambient"),
    ("Parchment Paper 2x250ft", ["parchment paper", "parchment", "baking paper"], "case", 2, 22, 18, 365, "ambient"),
    ("Trash Bags 55gal 100ct", ["trash bags", "garbage bags", "liners"], "case", 100, 45, 36, 365, "ambient"),
    ("Deli Containers 32oz 50ct", ["deli containers", "deli cups", "storage containers"], "case", 50, 18, 14, 365, "ambient"),
]
BEVERAGES: list[tuple[str, list[str], str, float, float, float, int, str]] = [
    ("Sparkling Water 24ct Case", ["sparkling water", "seltzer", "carbonated water"], "case", 24, 18, 14, 90, "ambient"),
    ("Orange Juice 4/1gal Case", ["orange juice", "oj", "juice"], "case", 4, 22, 18, 14, "refrigerated"),
    ("Apple Juice 4/1gal Case", ["apple juice", "juice"], "case", 4, 18, 14, 90, "ambient"),
    ("Cranberry Juice 4/1gal Case", ["cranberry juice", "cranberry", "juice"], "case", 4, 24, 19, 90, "ambient"),
    ("Lemonade 4/1gal Case", ["lemonade", "fresh lemonade"], "case", 4, 20, 16, 14, "refrigerated"),
    ("Iced Tea Gallon", ["iced tea", "tea", "sweet tea"], "each", 1, 6, 4.8, 14, "refrigerated"),
    ("Cola 24ct Case", ["cola", "soda", "coke", "soft drink"], "case", 24, 22, 18, 180, "ambient"),
    ("Diet Cola 24ct Case", ["diet cola", "diet soda", "diet coke"], "case", 24, 22, 18, 180, "ambient"),
    ("Ginger Ale 24ct Case", ["ginger ale", "soda", "ginger soda"], "case", 24, 20, 16, 180, "ambient"),
    ("Club Soda 24ct Case", ["club soda", "soda water", "seltzer"], "case", 24, 18, 14, 180, "ambient"),
    ("Energy Drink 24ct Case", ["energy drink", "energy drinks", "red bull"], "case", 24, 45, 36, 180, "ambient"),
    ("Bottled Water 24ct Case", ["bottled water", "water", "spring water"], "case", 24, 8, 6.4, 365, "ambient"),
    ("Coffee Beans 5lb Bag", ["coffee beans", "coffee", "whole bean"], "case", 5, 45, 36, 90, "ambient"),
    ("Espresso Beans 5lb Bag", ["espresso", "espresso beans", "coffee"], "case", 5, 55, 44, 90, "ambient"),
    ("Tea Bags 100ct Box", ["tea bags", "tea", "black tea"], "case", 100, 12, 9.6, 365, "ambient"),
]


def _expand(
    templates: list[tuple[str, list[str], str, float, float, float, int, str]],
    category: str,
    subcategory: str,
    prefix: str,
    target_count: int,
    supplier_ids: list[str],
) -> list[tuple[str, str, list[str], str, str, str, Decimal, Decimal, Decimal, int, str, str, str, None]]:
    out: list[tuple[str, str, list[str], str, str, str, Decimal, Decimal, Decimal, int, str, str, str, None]] = []
    for i in range(target_count):
        t = templates[i % len(templates)]
        name, aliases, uom, case_sz, up, cp, shelf, storage = t
        sku = f"{prefix}-{(i+1):03d}"
        # Slight price variance
        up_dec = Decimal(str(round(up * (0.95 + (i % 11) * 0.01), 2)))
        cp_dec = Decimal(str(round(cp * (0.95 + (i % 11) * 0.01), 2)))
        out.append((sku, name, aliases, category, subcategory, uom, Decimal(str(case_sz)), up_dec, cp_dec, shelf, storage, _pick(supplier_ids), "active", None))
    return out


async def run_seed() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        supplier_rows = await conn.fetch("SELECT supplier_id FROM suppliers")
        supplier_ids = [r["supplier_id"] for r in supplier_rows]
        await conn.execute("TRUNCATE TABLE order_items CASCADE")
        await conn.execute("TRUNCATE TABLE orders CASCADE")
        await conn.execute("TRUNCATE TABLE inventory CASCADE")
        await conn.execute("TRUNCATE TABLE supplier_products CASCADE")
        await conn.execute("TRUNCATE TABLE products CASCADE")

    all_products: list[tuple[str, str, list[str], str, str, str, Decimal, Decimal, Decimal, int, str, str, str, None]] = []
    all_products.extend(_expand(FRESH_FISH, "Seafood", "Fresh Fish", "SEA-FSH", 80, supplier_ids))
    all_products.extend(_expand(SHELLFISH, "Seafood", "Shellfish", "SEA-SHL", 50, supplier_ids))
    all_products.extend(_expand(FROZEN_FISH, "Seafood", "Frozen", "SEA-FRZ", 40, supplier_ids))
    all_products.extend(_expand(FRUITS, "Produce", "Fruits", "PRO-FRU", 80, supplier_ids))
    all_products.extend(_expand(VEGETABLES, "Produce", "Vegetables", "PRO-VEG", 80, supplier_ids))
    all_products.extend(_expand(DAIRY, "Dairy", "Dairy", "DAI", 60, supplier_ids))
    all_products.extend(_expand(DRY_GOODS, "Dry Goods", "Dry Goods", "DRY", 80, supplier_ids))
    all_products.extend(_expand(PAPER, "Paper & Supplies", "Supplies", "PAP", 50, supplier_ids))
    all_products.extend(_expand(BEVERAGES, "Beverages", "Beverages", "BEV", 80, supplier_ids))

    random.seed(42)
    random.shuffle(all_products)
    # Reassign SKUs so categories are mixed in ID space
    for i, row in enumerate(all_products):
        sku, name, aliases, cat, subcat, uom, case_sz, up, cp, shelf, storage, sup, status, emb = row
        new_sku = f"SKU-{(i+1):04d}"
        await execute(
            """INSERT INTO products (sku_id, name, aliases, category, subcategory, unit_of_measure, case_size, unit_price, cost_price, shelf_life_days, storage_type, supplier_id, status, embedding)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
            new_sku, name, aliases, cat, subcat, uom, case_sz, up, cp, shelf, storage, sup, status, emb,
        )
    print(f"Seeded {len(all_products)} products.")


if __name__ == "__main__":
    asyncio.run(run_seed())
