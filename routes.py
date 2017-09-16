# ----------------------------------------------------------------------------
# YoutubePiPlayer: Web remote for playing youtube videos with omxappli.player.
# Copyright (c) 2016-2017 Jules Lallouette
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# ----------------------------------------------------------------------------

from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, stream_with_context
from markdown import markdown

from application import *

#import logging
#logging.basicConfig(filename='/tmp/OMXWebInterface.log')

app = Flask(__name__)
appli = Application()

@app.route('/_getStatus')
def getStatus():
	oldHashes = request.args.get('updateHashes', '', type=str)
	oldHashes = json.loads(oldHashes)
	return jsonify(Status = appli.getStatus(), updatedParts = appli.getUpdatedParts(oldHashes))

@app.route('/_sendOrder')
def sendOrder():
	# TODO make all calls go through appli so it can be thread safe
	order = request.args.get('order', '', type=str)
	oldHashes = request.args.get('updateHashes', '', type=str)
	oldHashes = json.loads(oldHashes)
	if order in ['play','pause']:
		resul = appli.playPause()
		res = jsonify(result = resul)
	elif order == 'stop':
		res = jsonify(result = appli.player.stop())
	elif order == 'changeFormat':
		formatId = request.args.get('formatId', '0', int)
		ok = appli.setFormat(formatId)
		res = jsonify(result = ok)
	elif order == 'changePos':
		relPos = request.args.get('relPos', 0, type=float)
		res = jsonify(result=appli.player.setPosition(relPos * appli.player.getDuration()), position=appli.player.getPosition(), duration=appli.player.getDuration(), isPlaying = appli.player.isPlaying())
	elif order == 'selectRessource':
		resId = request.args.get('ressourceId', -1, type=int)
		ok = appli.selectPlaylist(resId)
		res = jsonify(result = ok, updatedParts = appli.getUpdatedParts(oldHashes))
	elif order == 'loadVideo':
		vidId = request.args.get('videoId', -1, type=int)
		ok = appli.loadVideo(vidId)
		res = jsonify(result = ok, updatedParts = appli.getUpdatedParts(oldHashes))
	elif order == 'processURL':
		urlPath = request.args.get('urlPath', '', type=str)
		name = request.args.get('name', '', type=str)
		ok = appli.processURL(urlPath, name)
		res = jsonify(result = ok, updatedParts = appli.getUpdatedParts(oldHashes))
	elif order == 'search':
		searchStr = request.args.get('searchString', '', type=str)
		ok = appli.searchFilter(searchStr)
		res = jsonify(result = ok, updatedParts = appli.getUpdatedParts(oldHashes))
	elif order == 'refreshRessource':
		plId = request.args.get('ressourceId', -1, type=int)
		ok = appli.refreshRessource(plId)
		res = jsonify(result = ok, updatedParts = appli.getUpdatedParts(oldHashes))
	return res

@app.route('/', methods=['GET','POST'])
def homepage():
	return render_template('index.html', cssPath=url_for('static', filename='css/base.css'), appli=appli)

if __name__ == '__main__':
	app.run(host='0.0.0.0',port=5002,debug=True, use_reloader=False, threaded=True)
