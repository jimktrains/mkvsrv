#!/usr/bin/env python3

import subprocess
from flask import Flask
from flask import request
from flask import send_file
from flask import g
from flask import render_template
from flask import send_from_directory
from flask import Response
import argparse
import json
import os
import sqlite3
import io
import tempfile

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

@app.route('/video/<service>/<service_id>/videofile')
def videofile(service, service_id):
    cur = get_db().cursor()
    res = cur.execute("""
select *
from video
where service = ?
  and service_id = ?
    """, (service, service_id))
    results = [dict(r) for r in res]
    if len(results) != 1:
        return render_template('404.jinja2.html')
    video = results[0]
    
    with tempfile.NamedTemporaryFile() as tf:
        print(tf.name)
        res = subprocess.run([f"ffmpeg", "-y", "-i", video['filepath'], "-c:v", "copy", "-c:a", "copy", "-f", "mp4", tf.name])#, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(res)
        return send_file(tf.name, mimetype='video/mp4')

@app.route('/video/<service>/<service_id>/chapters')
def chapters(service, service_id):
    cur = get_db().cursor()
    res = cur.execute("""
    select c.chapter_uid,
           c.start_ms,
           c.end_ms,
           chapterstring 
    from chapter c 
    join chapterdisplay cd on c.service = cd.service 
                          and c.service_id = cd.service_id
                          and c.chapter_uid = cd.chapter_uid
    where c.service_id = ?
    order by start_ms
    """, (service_id,))
    rawchapters = [dict(r) for r in res]
    chapters = []
    prevchap = None
    for chapter in rawchapters:
        s = float(chapter['start_ms']) / 1000.0
        hr = int(s / 3600)
        mn = int((s - (hr * 3600)) / 60)
        sec = s - (hr * 3600) - (mn * 60)
        chapter['from'] = f"{hr:02d}:{mn:02d}:{sec:06.3f}"
        if prevchap is not None:
            prevchap['to'] = chapter['from']
            chapters.append(prevchap)
        prevchap = chapter

    s = float(chapter['end_ms']) / 1000.0
    hr = int(s / 3600)
    mn = int((s - (hr * 3600)) / 60)
    sec = s - (hr * 3600) - (mn * 60)
    chapter['to'] = f"{hr:02d}:{mn:02d}:{sec:06.3f}"
    chapters.append(chapter)

    return render_template('chapters.jinja2.vtt', chapters=chapters)


@app.route('/video/<service>/<service_id>/thumbnail')
def thumbnail(service, service_id):
    cur = get_db().cursor()
    res = cur.execute("""
select *
from video
where service = ?
  and service_id = ?
    """, (service, service_id))
    results = [dict(r) for r in res]
    if len(results) != 1:
        return render_template('404.jinja2.html')
    video = results[0]
    result = subprocess.run(['mkvmerge', '--identification-format', 'json', '--identify', video['filepath']], stdout=subprocess.PIPE)
    if result.returncode != 0:
        print(result)
        exit(result.returncode)
    ident = json.loads(result.stdout)
    infojsonattachment = None
    for a in ident.get('attachments',[]):
        if a.get('file_name') == 'cover.webp':
            infojsonattachment = a
            break

    if infojsonattachment is None:
        print("Not attachment with a name of 'info.json' was found")
        exit(0)

    result = subprocess.run(['mkvextract', '--redirect-output', '/dev/null', video['filepath'], 'attachments', f"{a.get('id')}:/dev/stdout"], stdout=subprocess.PIPE)
    print(a)

    return send_file(
            io.BytesIO(result.stdout),
            download_name=a['file_name'],
            mimetype=a['content_type']
            )

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

    res = cur.execute("""
select tag
from ytvideotag
where video_id = ?
    """, (service_id,))
    tags = [r['tag'] for r in res]

    res = cur.execute("""
select category
from ytvideocategory
where video_id = ?
    """, (service_id,))
    categories = [r['category'] for r in res]

    return render_template('video.jinja2.html', video=video, tags=tags, categories=categories)

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
    artists = []
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
        results = [dict(r) for r in results]

        artists = cur.execute("""
select video.service,
       video.artist,
       ytvideo.uploader_id
from video
join ytvideo on ytvideo.video_id = video.service_id
    and video.service = 'youtube'
group by video.service,
         video.artist,
         ytvideo.uploader_id
order by video.artist
        """)
        artists = [dict(r) for r in artists]
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

        artists = cur.execute("""
select service,
       artist,
       uploader_id
from videosearch
join ytvideo on ytvideo.video_id = videosearch.service_id
    and videosearch.service = 'youtube'
where videosearch match ?
group by videosearch.service,
         videosearch.artist,
         ytvideo.uploader_id
order by artist
        """, (q,))
        artists = [dict(r) for r in artists]
    return render_template('home.jinja2.html', q=q or '', results=results, artists=artists)


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
