#!/usr/bin/env python3

from flask import Flask, request
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

@app.route('/video/<service>/<service_id>')
def video(service, service_id):
    cur = get_db().cursor()
    res = cur.execute("""
select *, uploader_id
from video
join ytvideo on ytvideo.video_id = video.service_id
    and video.service = 'youtube'
where service = ?
  and service_id = ?
    """, (service, service_id))
    results = [dict(r) for r in res]
    if len(results) != 1:
        return render_template('404.jinja2.html')
    video = results[0]
    return render_template('video.jinja2.html', video=video)

@app.route('/artist/<service>/<uploader_id>')
def artist(service, uploader_id):
    cur = get_db().cursor()
    res = cur.execute("""
select video.*
from video
join ytvideo on ytvideo.video_id = video.service_id
and video.service = 'youtube'
where video.service=? and ytvideo.uploader_id = ?
order by upload_date desc
    """, (service, uploader_id,))
    results = [dict(r) for r in res]
    if len(results) == 0:
        return render_template('404.jinja2.html')
    return render_template('artist.jinja2.html', results=results)

@app.route('/')
def home():
    args = request.args
    q = args.get('q')
    results = []
    cur = get_db().cursor()
    results = []
    if q is None:
        results = cur.execute("""
select video.service,
       video.service_id,
       video.artist,
       ytvideo.uploader_id,
       video.title as highlighttitle,
       video.description as highlightdesc
from video
join ytvideo on ytvideo.video_id = video.service_id
    and video.service = 'youtube'
order by video.upload_date desc
limit 25
        """)
    else:
        results = cur.execute("""
select service,
       service_id,
       artist,
       uploader_id,
       highlight(videosearch, 2, "<b>", "</b>") as highlighttitle,
       highlight(videosearch, 4, "<b>", "</b>") as highlightdesc
from videosearch
join ytvideo on ytvideo.video_id = videosearch.service_id
    and videosearch.service = 'youtube'
where videosearch match ?
order by bm25(videosearch, 0, 0, 20, 1, 2)
        """, (q,))

    results = [dict(r) for r in results]
    return render_template('home.jinja2.html', q=q or '', results=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", action="store", type=int, default=8000)
    parser.add_argument("-H", "--host", action="store", default="0.0.0.0")
    parser.add_argument('dbfile')
    args = parser.parse_args()


    with app.app_context():
        cur = get_db().cursor()
        print("Resetting search tables")
        cur.execute("delete from videosearch")
        print("Filling search tables")
        cur.execute('insert into videosearch select service, service_id, title, artist, description from video')
        cur.execute('commit')

    app.run(host=args.host, port=args.port)
