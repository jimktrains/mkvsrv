#!/usr/bin/env python3

from flask import Flask
from flask import g
from flask import render_template
import argparse
import json
import os
import sqlite3

app = Flask(__name__)

args = None


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(args.dbfile)
    db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def hello_world():
    cur = get_db().cursor()
    res = cur.execute('select * from video limit 1')
    x = [dict(r) for r in res]
    return json.dumps(x)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", action="store", type=int, default=8000)
    parser.add_argument("-H", "--host", action="store", default="0.0.0.0")
    parser.add_argument('dbfile')
    args = parser.parse_args()

    print("hello")
    app.run(host=args.host, port=args.port)
