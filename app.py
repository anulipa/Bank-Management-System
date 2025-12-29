# app.py (Python Flask Backend)

import os
from flask import Flask, request, jsonify, send_from_directory
import mysql.connector
from flask_bcrypt import Bcrypt
import jwt
from datetime import datetime, timedelta
from functools import wraps

# --- ক. কনফিগারেশন ও সেটআপ ---
app = Flask(__name__, static_url_path='/static', static_folder='static')
bcrypt = Bcrypt(app)
app.config['SECRET_KEY'] = 'account_no'

# --- খ. MySQL ডাটাবেস কনফিগারেশন ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root', 
    'password': '', 
    'database': 'bank_db',
    'raise_on_warnings': True
}

def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None 

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            try:
                token = request.headers['Authorization'].split(" ")[1]
            except IndexError:
                 return jsonify({'message': 'Token format is invalid!'}), 401
        if not token:
            return jsonify({'message': 'Access denied. Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            request.current_user = data 
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired! Please log in again.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(*args, **kwargs)
    return decorated

# --- ঘ. স্ট্যাটিক ফাইল রুট ---
@app.route('/')
@app.route('/<path:filename>')
def serve_static(filename='login.html'):
    return send_from_directory(app.static_folder, filename)

# --- ঙ. API এন্ডপয়েন্ট (API Endpoints) ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    account_no = data.get('account_no')
    pin = data.get('pin')

    if not account_no or not pin:
        return jsonify({'message': 'Account number and PIN are required'}), 400

    conn = get_db_connection()
    if conn is None: return jsonify({'message': 'Database unavailable'}), 503
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT account_no, name, pin FROM accounts WHERE account_no = %s", (account_no,))
        account = cursor.fetchone()

        if account and str(account['pin']) == str(pin):
            token = jwt.encode({'account_no': account['account_no'], 'exp': datetime.utcnow() + timedelta(hours=1)}, app.config['SECRET_KEY'], algorithm="HS256")
            return jsonify({'message': 'Login successful', 'token': token, 'name': account['name']})
        else:
            return jsonify({'message': 'Invalid Account Number or PIN'}), 401
    except Exception as e:
        print(f"Login Error: {e}")
        return jsonify({'message': 'Server error during login'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/accounts/balance', methods=['GET'])
@token_required
def get_balance():
    account_no = request.current_user['account_no']

    conn = get_db_connection()
    if conn is None: return jsonify({'message': 'Database unavailable'}), 503
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT account_no, name, balance FROM accounts WHERE account_no = %s", (account_no,))
        account = cursor.fetchone()

        if not account: return jsonify({'message': 'Account not found'}), 404

        return jsonify({'account': account})
    except Exception as e:
        print(f"Balance Error: {e}")
        return jsonify({'message': 'Server error fetching balance'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/transactions/deposit', methods=['POST'])
@token_required
def deposit():
    data = request.get_json()
    amount = data.get('amount')
    account_no = request.current_user['account_no']

    if not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({'message': 'Invalid deposit amount. Must be positive.'}), 400

    conn = get_db_connection()
    if conn is None: return jsonify({'message': 'Database unavailable'}), 503
    cursor = conn.cursor()
    
    try:
        conn.start_transaction()
        cursor.execute("UPDATE accounts SET balance = balance + %s WHERE account_no = %s", (amount, account_no))
        cursor.execute("INSERT INTO transactions (account_no, type, amount) VALUES (%s, %s, %s)", (account_no, 'Deposit', amount))
        cursor.execute("SELECT balance FROM accounts WHERE account_no = %s", (account_no,))
        new_balance = cursor.fetchone()[0]

        conn.commit()
        return jsonify({'message': 'Deposit successful', 'newBalance': new_balance})
        
    except Exception as e:
        conn.rollback()
        print(f"Deposit Error: {e}")
        return jsonify({'message': 'Server error during deposit'}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/transactions/withdraw', methods=['POST'])
@token_required
def withdraw():
    data = request.get_json()
    amount = data.get('amount')
    account_no = request.current_user['account_no']

    if not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({'message': 'Invalid withdraw amount. Must be positive.'}), 400

    conn = get_db_connection()
    if conn is None: return jsonify({'message': 'Database unavailable'}), 503
    cursor = conn.cursor()
    
    try:
        conn.start_transaction()
        cursor.execute("SELECT balance FROM accounts WHERE account_no = %s", (account_no,))
        current_balance = cursor.fetchone()[0]

        if current_balance < amount:
            conn.rollback()
            return jsonify({'message': 'Insufficient balance'}), 400

        cursor.execute("UPDATE accounts SET balance = balance - %s WHERE account_no = %s", (amount, account_no))
        cursor.execute("INSERT INTO transactions (account_no, type, amount) VALUES (%s, %s, %s)", (account_no, 'Withdraw', amount))
        
        new_balance = current_balance - amount
        conn.commit()

        return jsonify({'message': 'Withdrawal successful', 'newBalance': new_balance})
        
    except Exception as e:
        conn.rollback()
        print(f"Withdraw Error: {e}")
        return jsonify({'message': 'Server error during withdrawal'}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/transactions/transfer', methods=['POST'])
@token_required
def transfer():
    data = request.get_json()
    receiver_account_no = data.get('receiver_account_no')
    amount = data.get('amount')
    sender_account_no = request.current_user['account_no']

    if not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({'message': 'Invalid transfer amount. Must be positive.'}), 400
    if str(sender_account_no) == str(receiver_account_no):
        return jsonify({'message': 'Cannot transfer to the same account.'}), 400

    conn = get_db_connection()
    if conn is None: return jsonify({'message': 'Database unavailable'}), 503
    cursor = conn.cursor()
    
    try:
        conn.start_transaction()

        cursor.execute("SELECT balance FROM accounts WHERE account_no = %s", (sender_account_no,))
        sender_account_info = cursor.fetchone()
        
        if not sender_account_info:
            conn.rollback()
            return jsonify({'message': 'Sender account not found'}), 404
        
        sender_balance = sender_account_info[0]

        if sender_balance < amount:
            conn.rollback()
            return jsonify({'message': 'Insufficient balance for transfer'}), 400

        cursor.execute("SELECT account_no FROM accounts WHERE account_no = %s", (receiver_account_no,))
        if not cursor.fetchone():
            conn.rollback()
            return jsonify({'message': 'Receiver account not found'}), 404

        cursor.execute("UPDATE accounts SET balance = balance - %s WHERE account_no = %s", (amount, sender_account_no))
        cursor.execute("UPDATE accounts SET balance = balance + %s WHERE account_no = %s", (amount, receiver_account_no))

        cursor.execute("INSERT INTO transactions (account_no, type, amount, receiver_account) VALUES (%s, %s, %s, %s)", (sender_account_no, 'Transfer-Out', amount, receiver_account_no))
        cursor.execute("INSERT INTO transactions (account_no, type, amount, sender_account) VALUES (%s, %s, %s, %s)", (receiver_account_no, 'Transfer-In', amount, sender_account_no))
        
        new_balance = sender_balance - amount
        conn.commit()

        return jsonify({'message': 'Transfer successful', 'newBalance': new_balance})
        
    except Exception as e:
        conn.rollback()
        print(f"Transfer Error: {e}")
        return jsonify({'message': 'Server error during transfer'}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/accounts/history', methods=['GET'])
@token_required
def get_history():
    account_no = request.current_user['account_no']
    
    conn = get_db_connection()
    if conn is None: return jsonify({'message': 'Database unavailable'}), 503
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT DATE_FORMAT(date, '%%year-%%month-%%date %%hour:%%i') as date, type, amount FROM transactions WHERE account_no = %s ORDER BY date DESC LIMIT 10", 
            (account_no,)
        )
        history = cursor.fetchall()
        
        return jsonify({'history': history})
    except Exception as e:
        print(f"History Error: {e}")
        return jsonify({'message': 'Server error fetching history'}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    print("Starting Flask server on http://localhost:5000...")
    app.run(debug=True, port=5000)