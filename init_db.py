from app import app, db
# from app import Game, Player, BuyIn, Winner  # replace with your actual models

with app.app_context():
    db.create_all()
    print("Database tables created successfully.")
