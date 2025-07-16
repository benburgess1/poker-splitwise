from flask import Flask, render_template, request, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
import uuid
import os
from dotenv import load_dotenv

load_dotenv()
use_local = os.getenv("USE_LOCAL_DB", "False") == "True"

app = Flask(__name__)
if use_local:
    database_url = os.getenv("LOCAL_DATABASE_URL")
else:
    # On Render, DATABASE_URL is set automatically in the environment
    database_url = os.getenv("DATABASE_URL")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
# app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
# app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///poker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models

class Game(db.Model):
    id = db.Column(db.String(36), primary_key=True)  # use UUID string
    name = db.Column(db.String(100), nullable=False)
    settled = db.Column(db.Boolean, default=False)
    players = db.relationship('Player', backref='game', cascade='all, delete-orphan', lazy=True)
    buyins = db.relationship('BuyIn', backref='game', cascade='all, delete-orphan', lazy=True)
    winners = db.relationship('Winner', backref='game', cascade='all, delete-orphan', lazy=True)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    game_id = db.Column(db.String(36), db.ForeignKey('game.id'), nullable=False)
    buyins = db.relationship('BuyIn', backref='player', cascade='all, delete-orphan', lazy=True)
    winnings = db.relationship('Winner', backref='player', cascade='all, delete-orphan', lazy=True)

class BuyIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    game_id = db.Column(db.String(36), db.ForeignKey('game.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)

class Winner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.String(36), db.ForeignKey('game.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    percentage = db.Column(db.Float, default=100.0)
    name = db.Column(db.String(100), nullable=False)


# Routes

@app.route('/')
def home():
    games = Game.query.all()
    return render_template('home.html', games=games)


@app.route("/new", methods=["GET", "POST"])
def new_game():
    if request.method == "POST":
        game_name = request.form.get("game_name")
        if not game_name:
            return "Missing game name", 400

        game_id = str(uuid.uuid4())
        new_game = Game(id=game_id, name=game_name)
        db.session.add(new_game)
        db.session.commit()
        return redirect(url_for("game_detail", game_id=game_id))

    return render_template("new_game.html")


@app.route("/game/<game_id>")
def game_detail(game_id):
    game = Game.query.get(game_id)
    if not game:
        abort(404)

    players = Player.query.filter_by(game_id=game_id).all()
    buyins = BuyIn.query.filter_by(game_id=game_id).all()
    winners = Winner.query.filter_by(game_id=game_id).all()

    # Prepare winnings dict for template (player name -> percentage)
    winnings = {}
    for w in winners:
        winnings[w.player.name] = w.percentage

    return render_template("game_detail.html", game=game, players=players, buyins=buyins, winnings=winnings, game_id=game_id)


@app.route("/game/<game_id>/add_player", methods=["POST"])
def add_player(game_id):
    player_name = request.form["player_name"].strip()
    if not player_name:
        return redirect(url_for("game_detail", game_id=game_id))

    game = Game.query.get(game_id)
    if not game:
        abort(404)

    # Check if player already exists in this game
    exists = Player.query.filter_by(game_id=game_id, name=player_name).first()
    if not exists:
        player = Player(name=player_name, game_id=game_id)
        db.session.add(player)
        db.session.commit()

    return redirect(url_for("game_detail", game_id=game_id))


@app.route("/game/<game_id>/add_buyin", methods=["POST"])
def add_buyin(game_id):
    player_name = request.form["player"]
    amount = request.form.get("amount")
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return redirect(url_for("game_detail", game_id=game_id))

    game = Game.query.get(game_id)
    if not game:
        abort(404)

    player = Player.query.filter_by(game_id=game_id, name=player_name).first()
    if not player:
        # Player must exist to add buyin
        return redirect(url_for("game_detail", game_id=game_id))

    buyin = BuyIn(player_id=player.id, game_id=game_id, amount=amount)
    db.session.add(buyin)
    db.session.commit()

    return redirect(url_for("game_detail", game_id=game_id))


@app.route("/game/<game_id>/assign_winner", methods=["GET", "POST"])
def assign_winner(game_id):
    game = Game.query.get(game_id)
    if not game:
        abort(404)

    players = Player.query.filter_by(game_id=game_id).all()

    winner_lookup = {
    winner.player_id: winner.percentage
    for winner in game.winners
    }

    if request.method == "POST":
        # Clear existing winnings
        Winner.query.filter_by(game_id=game_id).delete()

        # Parse winners and percentages
        for player in players:
            percent_str = request.form.get(player.name)
            if percent_str:
                try:
                    percent = float(percent_str)
                    if percent > 0:
                        winner = Winner(game_id=game_id, player_id=player.id, percentage=percent, name=player.name)
                        db.session.add(winner)
                except ValueError:
                    pass  # Ignore invalid numbers

        db.session.commit()
        return redirect(url_for("game_detail", game_id=game_id))

    return render_template("assign_winner.html", game=game, players=players, winner_lookup=winner_lookup)


@app.route("/delete_player/<game_id>/<int:player_id>", methods=["POST"])
def delete_player(game_id, player_id):
    player = Player.query.filter_by(id=player_id, game_id=game_id).first()
    if not player:
        abort(404)

    db.session.delete(player)
    db.session.commit()
    return redirect(url_for("game_detail", game_id=game_id))


@app.route("/delete_buyin/<game_id>/<int:buyin_id>", methods=["POST"])
def delete_buyin(game_id, buyin_id):
    buyin = BuyIn.query.filter_by(id=buyin_id, game_id=game_id).first()
    if not buyin:
        abort(404)

    db.session.delete(buyin)
    db.session.commit()
    return redirect(url_for("game_detail", game_id=game_id))


@app.route("/settle_game/<game_id>", methods=["POST"])
def settle_game(game_id):
    game = Game.query.get(game_id)
    if not game:
        abort(404)

    game.settled = True
    db.session.commit()
    return redirect(url_for("games_summary"))


@app.route("/reactivate_game/<game_id>", methods=["POST"])
def reactivate_game(game_id):
    game = Game.query.get(game_id)
    if not game:
        abort(404)

    game.settled = False
    db.session.commit()
    return redirect(url_for("games_summary"))


def simplify_debts(net_balances):
    owes = []
    owed = []
    for player, amount in net_balances.items():
        if amount < -1e-6:
            owes.append([player, -amount])
        elif amount > 1e-6:
            owed.append([player, amount])

    owes.sort(key=lambda x: x[1])
    owed.sort(key=lambda x: x[1])

    debts = []
    i, j = 0, 0
    while i < len(owes) and j < len(owed):
        pay_amt = min(owes[i][1], owed[j][1])
        debts.append((owes[i][0], owed[j][0], pay_amt))
        owes[i][1] -= pay_amt
        owed[j][1] -= pay_amt
        if owes[i][1] < 1e-6:
            i += 1
        if owed[j][1] < 1e-6:
            j += 1

    return debts


@app.route("/summary")
def summary():
    net_balances = {}

    games = Game.query.all()
    for game in games:
        buyin_totals = {}
        for b in game.buyins:
            buyin_totals[b.player.name] = buyin_totals.get(b.player.name, 0) + b.amount

        winnings = {w.player.name: w.percentage for w in game.winners}
        total_pot = sum(buyin_totals.values())

        players = [p.name for p in game.players]

        for player in players:
            won_amount = (winnings.get(player, 0) / 100) * total_pot if winnings else 0
            net = won_amount - buyin_totals.get(player, 0)
            net_balances[player] = net_balances.get(player, 0) + net

    debts = simplify_debts(net_balances)

    return render_template("summary.html", games=games, debts=debts, net_balances=net_balances)


@app.route("/debts")
def debts_summary():
    net_balances = {}

    games = Game.query.all()

    for game in games:
        if game.settled:
            # skip settled games
            continue

        buyin_totals = {}
        for b in game.buyins:
            buyin_totals[b.player.name] = buyin_totals.get(b.player.name, 0) + b.amount

        winnings = {w.player.name: w.percentage for w in game.winners}
        total_pot = sum(buyin_totals.values())

        players = [p.name for p in game.players]

        for player in players:
            won_amount = (winnings.get(player, 0) / 100) * total_pot if winnings else 0
            net = won_amount - buyin_totals.get(player, 0)
            net_balances[player] = net_balances.get(player, 0) + net

    debts = simplify_debts(net_balances)

    return render_template("debts_summary.html", games=games, debts=debts, net_balances=net_balances)


@app.route("/games")
def games_summary():
    active_games = Game.query.filter_by(settled=False).all()
    settled_games = Game.query.filter_by(settled=True).all()
    return render_template("games_summary.html", active_games=active_games, settled_games=settled_games)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

# from flask import Flask, render_template, request, redirect, url_for
# from flask_sqlalchemy import SQLAlchemy # ignore warning
# import uuid

# app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///poker.db'
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # silence warning

# db = SQLAlchemy(app)

# # games = {}  # In-memory database substitute for now

# class Game(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     settled = db.Column(db.Boolean, default=False)
#     players = db.relationship('Player', backref='game', cascade="all, delete-orphan")
#     buyins = db.relationship('BuyIn', backref='game', cascade="all, delete-orphan")
#     winners = db.relationship('Winner', backref='game', cascade="all, delete-orphan")

# class Player(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     game_id = db.Column(db.Integer, db.ForeignKey('game.id'))

# class BuyIn(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
#     game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
#     amount = db.Column(db.Float, nullable=False)
#     times = db.Column(db.Integer, default=1)

# class Winner(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
#     player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
#     percentage = db.Column(db.Float, default=100.0)


# @app.route('/')
# def home():
#     return render_template('home.html', games=games)

# @app.route("/new", methods=["GET", "POST"])
# def new_game():
#     if request.method == "POST":
#         game_name = request.form.get("game_name")
#         if not game_name:
#             return "Missing game name", 400

#         game_id = str(uuid.uuid4())
#         games[game_id] = {
#             "name": game_name,
#             "players": [],
#             "buyins": [],
#             "winnings": {},
#             "settled": False
#         }
#         return redirect(url_for("game_detail", game_id=game_id))

#     return render_template("new_game.html")


# @app.route("/game/<game_id>")
# def game_detail(game_id):
#     game = games.get(game_id)
#     if not game:
#         return "Game not found", 404
#     return render_template("game_detail.html", game=game, game_id=game_id)


# @app.route("/game/<game_id>/add_player", methods=["POST"])
# def add_player(game_id):
#     player_name = request.form["player_name"]
#     if game_id in games and player_name not in games[game_id]["players"]:
#         games[game_id]["players"].append(player_name)
#     return redirect(url_for("game_detail", game_id=game_id))


# @app.route("/game/<game_id>/add_buyin", methods=["POST"])
# def add_buyin(game_id):
#     player = request.form["player"]
#     amount = float(request.form["amount"])
#     if game_id in games:
#         games[game_id]["buyins"].append({"player": player, "amount": amount})
#     return redirect(url_for("game_detail", game_id=game_id))


# @app.route("/game/<game_id>/assign_winner", methods=["GET", "POST"])
# def assign_winner(game_id):
#     game = games.get(game_id)
#     if not game:
#         return "Game not found", 404

#     if request.method == "POST":
#         # Clear existing winnings
#         game["winnings"] = {}

#         # Parse winners and percentages
#         for player in game["players"]:
#             percent_str = request.form.get(player)
#             if percent_str:
#                 try:
#                     percent = float(percent_str)
#                     if percent > 0:
#                         game["winnings"][player] = percent
#                 except ValueError:
#                     pass  # Ignore invalid numbers

#         return redirect(url_for("game_detail", game_id=game_id))

#     return render_template("assign_winner.html", game=game, game_id=game_id)

# @app.route("/delete_player/<game_id>/<player_name>", methods=["POST"])
# def delete_player(game_id, player_name):
#     game = games.get(game_id)
#     if not game:
#         return "Game not found", 404

#     # Remove player from players list
#     if player_name in game["players"]:
#         game["players"].remove(player_name)

#     # Remove buyins by this player
#     game["buyins"] = [b for b in game["buyins"] if b["player"] != player_name]

#     # Remove winnings entry if present
#     if game.get("winnings") and player_name in game["winnings"]:
#         game["winnings"].pop(player_name)

#     return redirect(url_for("game_detail", game_id=game_id))


# @app.route("/delete_buyin/<game_id>/<int:buyin_index>", methods=["POST"])
# def delete_buyin(game_id, buyin_index):
#     game = games.get(game_id)
#     if not game:
#         return "Game not found", 404

#     if 0 <= buyin_index < len(game["buyins"]):
#         game["buyins"].pop(buyin_index)

#     return redirect(url_for("game_detail", game_id=game_id))


# @app.route("/settle_game/<game_id>", methods=["POST"])
# def settle_game(game_id):
#     game = games.get(game_id)
#     if not game:
#         return "Game not found", 404

#     game["settled"] = True
#     return redirect(url_for("games_summary"))

# @app.route("/reactivate_game/<game_id>", methods=["POST"])
# def reactivate_game(game_id):
#     game = games.get(game_id)
#     if not game:
#         return "Game not found", 404

#     game["settled"] = False
#     return redirect(url_for("games_summary"))

# def simplify_debts(net_balances):
#     """ 
#     net_balances: dict player -> net amount (positive means owed money, negative means owes)
#     Returns a list of simplified debts like (payer, receiver, amount)
#     """
#     # Separate who owes and who is owed
#     owes = []
#     owed = []
#     for player, amount in net_balances.items():
#         if amount < -1e-6:
#             owes.append([player, -amount])  # store positive owed amount
#         elif amount > 1e-6:
#             owed.append([player, amount])

#     owes.sort(key=lambda x: x[1])
#     owed.sort(key=lambda x: x[1])

#     debts = []
#     i, j = 0, 0

#     while i < len(owes) and j < len(owed):
#         pay_amt = min(owes[i][1], owed[j][1])
#         debts.append((owes[i][0], owed[j][0], pay_amt))
#         owes[i][1] -= pay_amt
#         owed[j][1] -= pay_amt
#         if owes[i][1] < 1e-6:
#             i += 1
#         if owed[j][1] < 1e-6:
#             j += 1

#     return debts

# @app.route("/summary")
# def summary():
#     # Aggregate net balances
#     net_balances = {}

#     for game in games.values():
#         # sum buy-ins per player
#         buyin_totals = {}
#         for b in game["buyins"]:
#             buyin_totals[b["player"]] = buyin_totals.get(b["player"], 0) + b["amount"]
        
#         # sum winnings per player (percentage of total pot)
#         winnings = game.get("winnings", {})
#         total_pot = sum(buyin_totals.values())
        
#         for player in game["players"]:
#             won_amount = (winnings.get(player, 0) / 100) * total_pot if winnings else 0
#             net = won_amount - buyin_totals.get(player, 0)
#             net_balances[player] = net_balances.get(player, 0) + net

#     debts = simplify_debts(net_balances)

#     return render_template("summary.html", games=games, debts=debts, net_balances=net_balances)


# @app.route("/games")
# def games_summary():
#     active_games = {gid: g for gid, g in games.items() if not g.get("settled", False)}
#     settled_games = {gid: g for gid, g in games.items() if g.get("settled", False)}
#     return render_template("games_summary.html", active_games=active_games, settled_games=settled_games)


# @app.route("/debts")
# def debts_summary():
#     net_balances = {}

#     for game in games.values():
#         if game.get("settled", False):
#             # skip settled games
#             continue

#         buyin_totals = {}
#         for b in game["buyins"]:
#             buyin_totals[b["player"]] = buyin_totals.get(b["player"], 0) + b["amount"]

#         winnings = game.get("winnings", {})
#         total_pot = sum(buyin_totals.values())

#         for player in game["players"]:
#             won_amount = (winnings.get(player, 0) / 100) * total_pot if winnings else 0
#             net = won_amount - buyin_totals.get(player, 0)
#             net_balances[player] = net_balances.get(player, 0) + net

#     debts = simplify_debts(net_balances)
#     return render_template("debts_summary.html", debts=debts)


# if __name__ == '__main__':
#     app.run(debug=True, host='0.0.0.0')

