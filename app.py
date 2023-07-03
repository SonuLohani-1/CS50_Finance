import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

from datetime import datetime

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    user_portfolio = db.execute("SELECT * FROM user_stocks WHERE user_id = ?", user_id)
    cash = db.execute("SELECT * FROM users WHERE id=?", user_id)
    curr_price = []
    total_share_price = 0
    for row in user_portfolio:
        stock_info = lookup(row["stock_name"])
        curr_price.append(stock_info["price"])
        total_share_price += stock_info["price"] * row["units"]
    return render_template(
        "index.html",
        user_portfolio=user_portfolio,
        curr_price=curr_price,
        cash=cash[0]["cash"],
        total_share_price=total_share_price,
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        num = request.form.get("shares")
        if num.isdigit():
            num = int(num)
        else:
            return apology("Enter a Valid Number")

        symbol = request.form.get("symbol")
        user_id = session["user_id"]
        amt_available_data = db.execute("SELECT * FROM users WHERE id=?", user_id)
        amt_available = amt_available_data[0]["cash"]
        if symbol == "":
            return apology("Please Enter a valid stock symbol")
        quote = lookup(symbol)
        if num <= 0:
            return apology("Please enter a positive number")
        elif quote is None:
            return apology("Please enter a valid stock symbol")
        elif float(amt_available / num) < quote["price"]:
            return apology("Fund are not enough to buy that many stocks")
        else:
            # Buy the particular number of stock and update the database
            # first find if the user already owns this stock
            isOwed = db.execute(
                "SELECT * FROM user_stocks WHERE user_id = ? AND stock_name = ?",
                user_id,
                quote["symbol"],
            )
            # if user already owns that stock we will update the user_stocks database
            if len(isOwed) != 0:
                db.execute(
                    "UPDATE user_stocks SET units = units + ? WHERE user_id = ? AND stock_name = ?",
                    num,
                    user_id,
                    quote["symbol"],
                )
                # also edit the users table to update the available balance
                db.execute(
                    "UPDATE users SET cash = cash - ? WHERE id = ?",
                    num * quote["price"],
                    user_id,
                )
                # add  that stock in the user_stocks database
            else:
                db.execute(
                    "INSERT INTO user_stocks (user_id, stock_name, units) VALUES (?, ?, ?)",
                    user_id,
                    quote["symbol"],
                    num,
                )
                # also edit the users table to update the available balance
                db.execute(
                    "UPDATE users SET cash = cash - ? WHERE id = ?",
                    num * quote["price"],
                    user_id,
                )

            # updating the history table to store the following buyings:
            # Get the current date and time
            current_datetime = datetime.now()
            curr_date = current_datetime.date()
            curr_time = current_datetime.time()
            db.execute(
                "INSERT INTO transactions (user_id, action, stock_name, time, date, price) VALUES  (?, ?, ?, ?, ?, ?)",
                user_id,
                num,
                quote["symbol"],
                curr_time,
                curr_date,
                quote["price"],
            )

            return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", user_id)

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock_symbol = request.form.get("symbol")
        quote = lookup(stock_symbol)
        if quote is None:
            return apology("Stock doesn't exist")
        else:
            return render_template("quoted.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirmation")

        # checking if the username is already taken:
        is_username_taken = db.execute(
            "SELECT * FROM users WHERE username = ?", username
        )
        if "" in [username, password, confirm_password]:
            return apology("All fields are required.")
        elif password != confirm_password:
            return apology("Passwords didn't match")
        # finaly checking if the user name is already taken
        elif len(is_username_taken) != 0:
            return apology("Username already taken")
        else:
            hash_password = generate_password_hash(password)
            db.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?)",
                username,
                hash_password,
            )

        user_id = db.execute("SELECT * FROM users WHERE username=?", username)
        session["user_id"] = user_id[0]["id"]
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    if request.method == "POST":
        # getting the list of stocks owned by the user
        user_portfolio = db.execute(
            "SELECT * FROM user_stocks WHERE user_id=?", user_id
        )
        print(user_portfolio)
        stock_to_sell = request.form.get("symbol")
        units_to_sell = request.form.get("shares")
        units_available = db.execute(
            "SELECT * FROM user_stocks WHERE user_id=? AND stock_name=?",
            user_id,
            stock_to_sell,
        )
        units_available_count = units_available[0]["units"]
        found = any(item.get("stock_name") == stock_to_sell for item in user_portfolio)
        if not found:
            return apology("stock not owned")
        # if user has not entered a number then return apology
        if not units_to_sell.isnumeric():
            return apology("please enter a valid number")
        # else checking for units if that many units are owned by the user
        elif int(units_to_sell) > units_available_count:
            return apology("Not as many stocks to sell")

        # Now selling the stock
        # We will have to update two tables
        # first changing the cash value in users table
        # second stocks count in the user_stocks table
        # if user sells all the shares of a stock we will delete that row

        curr_price = lookup(stock_to_sell)["price"]
        units_to_sell = int(units_to_sell)
        if units_to_sell == units_available_count:
            db.execute(
                "DELETE FROM user_stocks WHERE user_id = ? AND stock_name = ?",
                user_id,
                stock_to_sell,
            )

        else:
            # update the user_stocks table
            db.execute(
                "UPDATE user_stocks SET units = units - ? WHERE user_id = ? AND stock_name = ?",
                units_to_sell,
                user_id,
                stock_to_sell,
            )

        # also updating the cash available in the table
        db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?",
            units_to_sell * curr_price,
            user_id,
        )

        # updating the history table to store the following buyings:
        # Get the current date and time
        current_datetime = datetime.now()
        curr_date = current_datetime.date()
        curr_time = current_datetime.time()
        db.execute(
            "INSERT INTO transactions (user_id, action, stock_name, time, date, price) VALUES  (?, ?, ?, ?, ?, ?)",
            user_id,
            -units_to_sell,
            stock_to_sell,
            curr_time,
            curr_date,
            curr_price,
        )

        return redirect("/")
    else:
        user_portfolio = db.execute(
            "SELECT * FROM user_stocks WHERE user_id=?", user_id
        )
        return render_template("sell.html", user_portfolio=user_portfolio)
