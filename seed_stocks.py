from models import SessionLocal, Stock

stock_items = [
    # Panels - 3/4"
    {"name": "3/4 Panel", "description": ".55 Density", "quantity": 0, "unit": "sheets"},
    {"name": "3/4 Panel", "description": ".52 Density", "quantity": 0, "unit": "sheets"},
    {"name": "3/4 Panel", "description": "Eazy Board", "quantity": 0, "unit": "sheets"},

    # Panels - 1/2"
    {"name": "1/2 Panel", "description": ".55 Density", "quantity": 0, "unit": "sheets"},
    {"name": "1/2 Panel", "description": ".52 Density", "quantity": 0, "unit": "sheets"},
    {"name": "1/2 Panel", "description": "Eazy Board", "quantity": 0, "unit": "sheets"},

    # Panels - 1/4"
    {"name": "1/4 Panel", "description": ".55 Density", "quantity": 0, "unit": "sheets"},
    {"name": "1/4 Panel", "description": ".52 Density", "quantity": 0, "unit": "sheets"},
    {"name": "1/4 Panel", "description": "Eazy Board", "quantity": 0, "unit": "sheets"},

    # Other materials
    {"name": "Laminate", "description": "Enter code and color manually", "quantity": 0, "unit": "sheets"},
    {"name": "Contact Cement", "description": "5 Gallon Container", "quantity": 0, "unit": "buckets"},
    {"name": "Drawer Slides", "description": "Full Extension", "quantity": 0, "unit": "pairs"},
    {"name": "Drawer Slides", "description": "Soft Close", "quantity": 0, "unit": "pairs"},
    {"name": "Hinges", "description": "Regular", "quantity": 0, "unit": "pieces"},
    {"name": "Hinges", "description": "Soft Close", "quantity": 0, "unit": "pieces"},
    {"name": "Mineral Spirits", "description": "", "quantity": 0, "unit": "gallons"},
    {"name": "Liquid Thinner", "description": "", "quantity": 0, "unit": "gallons"},

    # Screws
    {"name": "Screws", "description": "3 inch", "quantity": 0, "unit": "boxes"},
    {"name": "Screws", "description": "2 inch", "quantity": 0, "unit": "boxes"},
    {"name": "Screws", "description": "1.5 inch", "quantity": 0, "unit": "boxes"},
    {"name": "Screws", "description": "1.25 inch", "quantity": 0, "unit": "boxes"},
    {"name": "Screws", "description": "1 inch", "quantity": 0, "unit": "boxes"},
    {"name": "Screws", "description": "3/4 inch", "quantity": 0, "unit": "boxes"},
    {"name": "Screws", "description": "5/8 inch", "quantity": 0, "unit": "boxes"},
]

db = SessionLocal()
for item in stock_items:
    existing = db.query(Stock).filter_by(name=item["name"], description=item["description"]).first()
    if not existing:
        db.add(Stock(**item))

db.commit()
db.close()
print("✅ Stock items added.")
