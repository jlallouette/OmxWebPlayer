import subprocess
from multiprocessing import Queue
import json
import datetime
import re
from time import sleep, time
from flask import Markup
from peewee import *
import glob
import os

##################
# Database stuff #
##################


dbFilePath = 'data.sql'
db = SqliteDatabase(dbFilePath, pragmas=(('foreign_keys', 'on'),))

class BaseModel(Model):
    class Meta:
        database = db

#####################
# Utility functions #
#####################

def ProcessPathURL(urlPath, name, pl = None, changeCallBack = None, lock = None, slow = False):
	# Determine if the urlPath is an URL or a local path
	urlre = re.compile('^https?://.+')
	if urlre.match(urlPath):
		with lock:
			defaultPl = Parameters.get().defaultPlaylist if not pl else pl
		return ProcessYoutubeURL(urlPath, name, defaultPl, changeCallBack, lock)
	else:
		return ProcessPath(urlPath, name, pl, changeCallBack, lock, slow = slow)

# Scans a path and adds all the videos to the database
# Creates a new playlist for each non empty subfolder 
def ProcessPath(path, name, pl = None, changeCallBack = None, lock = None, firstCall=True, slow = False):
	with lock:
		params = Parameters.get()
		extRe=re.compile('(.*?)\.(' + '|'.join(params.extensions.split()) + ')$')
		defaultPl = Parameters.get().defaultPlaylist
		sleepTime = Parameters.get().backgroundSleepTime
	allPl = []
	for dirpath, dirNames, fileNames in os.walk(path):
		vidFileMatch = list(filter(lambda x: x, map(extRe.match, fileNames)))
		if len(vidFileMatch) + len(dirNames) > 0:

			with lock:
				if Playlist.select().where(Playlist.URL == dirpath).count() == 0:
					currPl = Playlist.create(URL = dirpath, name = os.path.basename(dirpath) if pl else name, parent = pl, depth = pl.depth + 1 if pl else 0)
					currPl.addedTotVideos(len(vidFileMatch))
				else:
					currPl = Playlist.get(Playlist.URL == dirpath)
			allPl.append(currPl)

			changeCallBack(currPl)

			# Add video Files
			allVidPaths = []
			for vfm in vidFileMatch:
				vidPath = os.path.join(dirpath, vfm.group(0))
				allVidPaths.append(vidPath)
				with lock:
					alreadyExist = Video.select().where(Video.path == vidPath).count() > 0
				if not alreadyExist:
					# Duration, resolution etc are extracted in a separate thread
					dur = 10
					res = '10x10'
					okFormats = [{'name':'Auto', 'url':''},{'name':res, 'url':vidPath}]
					with lock:
						vid = Video.create(origURL = vidPath, path = vidPath, title = vfm.group(1), duration=dur, playlist = currPl, okFormatsList = json.dumps(okFormats), needsInfoExtract = True)
						currPl.addedVideos(1)

					changeCallBack(currPl)
				if slow:
					sleep(sleepTime)

			# Remove deleted or unaccessible videos
			with lock:
				nbOrphans = Video.select().where((Video.playlist == currPl) & ~(Video.path << allVidPaths)).count()
				if nbOrphans > 0:
					Video.delete().where((Video.playlist == currPl) & ~(Video.path << allVidPaths)).execute()
					currPl.addedTotVideos(-nbOrphans)
					currPl.addedVideos(-nbOrphans)
					changeCallBack(currPl)

			# Add subdirectories
			for dirn in dirNames:
				allPl += ProcessPath(os.path.join(path, dirn), name, currPl, changeCallBack, lock, firstCall=False, slow = slow) 

			# Delete empty playlists
			with lock:
				if currPl.totAllNbVids == 0:
					Playlist.delete().where(Playlist.id == currPl.id).execute()
					currPl = None
				else:
					currPl.justCreated = False
					currPl.save()
		break

	# Delete orphan playlists
	if firstCall and pl:
		with lock:
			allPlPaths = [pp.URL for pp in allPl]
			allOrphansId = [p.id for p in pl.getAllChildren() if p.URL not in allPlPaths]
			nbOrphans = Playlist.select().where(Playlist.id << allOrphansId).count()
			if nbOrphans > 0:
				Playlist.delete().where(Playlist.id << allOrphansId).execute()
	return allPl


def ProcessYoutubeURL(url, name, pl=None, changeCallBack=None, lock = None, vid=None):#, progressQueue = None):
	# First check that url hasn't already been loaded as a video
	if vid or Video.select().where(Video.origURL == url).count() == 0:
		with lock:
			params = Parameters.get()
		cmdLine = 'youtube-dl -j --flat-playlist --all-subs '
		if params.ytUsername:
			cmdLine += '-u ' + params.ytUsername + ' -p ' + params.ytPassword + ' '
		if params.cookiesPath:
			cmdLine += '--cookies ' + params.cookiesPath + ' '
		cmd = subprocess.Popen(cmdLine + '"' + url + '"', shell=True, stdout=subprocess.PIPE)
		isPlaylist = False
		infos = []
		for line in cmd.stdout:
			infos.append(json.loads(line.decode()))
			if 'formats' not in infos[-1]:
				isPlaylist = True
		
		if len(infos) > 0:
			if isPlaylist:
				# If the playlist already exists, just update the videos
				with lock:
					existPl = Playlist.get(Playlist.URL == url) if Playlist.select().where(Playlist.URL == url).count() > 0 else None
				return InsertYtPlaylist(infos, url, name, existPl, changeCallBack, lock)#, progressQueue)
			else:
				return InsertYtVideo(infos[0], url, pl, lock, vid)
		else:
			return None
	else:
		with lock:
			return Video.get(Video.origURL == url)

# Inserts the playlist and its videos in the database
def InsertYtPlaylist(infos, url, name, existPl = None, changeCallBack=None, lock = None):
	with lock:
		if existPl:
			pl = existPl
			pl.addedTotVideos(-pl.totNbVids)
			pl.addedVideos(-pl.nbVids)
			pl.addedTotVideos(len(infos))
			#pl.totNbVids = len(infos)
			#pl.save()
		else:
			pl = Playlist.create(URL = url, name = name)
			pl.addedTotVideos(len(infos))
	changeCallBack(pl)

	changed = False
	for info in infos:
		with lock:
			vidDidntExist = (Video.select().where(Video.origURL == info['url']).count() == 0)
			changed = changed or vidDidntExist
			vid = None if vidDidntExist else Video.get(Video.origURL == info['url'])
		if vidDidntExist:
			ProcessYoutubeURL(info['url'], '', pl, changeCallBack, lock, vid)
		else:
			with lock:
				pl.addedVideos(1)
		changeCallBack(pl)

	# Remove videos that were deleted from the playlist
	# TODO Call the correct functions for computing nb of videos
	if existPl:
		allUrls = [info['url'] for info in infos]
		with lock:
			nbOrphans = Video.select().where((Video.playlist == existPl) & ~(Video.origURL << allUrls)).count()
			if nbOrphans > 0:
				changed = True
				Video.delete().where((Video.playlist == existPl) & ~(Video.origURL << allUrls)).execute()
				#existPl.addedTotVideos(-nbOrphans)
				#existPl.addedVideos(-nbOrphans)
		# If the playlist was changed, mark it as changed
		if changed and changeCallBack:
			changeCallBack(existPl)
	with lock:
		pl.justCreated = False
		pl.save()
	return pl

# Inserts a youtube video in the database
def InsertYtVideo(infos, origURL, pl = None, lock = None, vid = None):
	# description 
	descr = ''
	if 'description' in infos:
		descr = infos['description']
		descr = descr.replace('\n', ' <br/> ')
		descr = re.sub('https?://[^\s]+\s?', lambda x:'<a href="'+x.group(0)+'">'+x.group(0)+'</a>', descr)
	url = infos['webpage_url']
	vidId = infos['id']
	# Handle the format list
	p = re.compile('.*[^0-9]+((\d+)x\d+).*');
	formats = [f for f in infos['formats'] if ('only' not in f['format']) and ('video' not in f['format'])]
	okFormats = [{'name':'Auto', 'url':''}]
	for f in sorted(formats, key=lambda f:int(p.match(f['format']).group(2)), reverse=True):
		okFormats.append({'name':p.match(f['format']).group(1),'url':f['url']})
	# Expiration time for the streams
	p2 = re.compile('.*expire=(\d+)&.*')
	exp = None
	if len(okFormats) > 0:
		for f in okFormats:
			m = p2.match(f['url'])
			if m:
				break
		if m:
			exp = datetime.datetime.fromtimestamp(int(m.group(1)))
	if vid:
		# Update the video
		vid.title = infos['title']
		vid.description = descr
		vid.infos = json.dumps(infos)
		vid.okFormatsList = json.dumps(okFormats)
		vid.expires = exp
		vid.save()
		return vid
	else:
		# Add the video to the database
		with lock:
			# Update video counters
			pl.addedVideos(1)
			if pl.id == Parameters.get().defaultPlaylist.id:
				pl.addedTotVideos(1)
			return Video.create(videoId = vidId, origURL = origURL, URL = url, title = infos['title'], description = descr, duration = infos['duration'], thumbnailURL = infos['thumbnails'][0]['url'], playlist = pl, infos = json.dumps(infos), okFormatsList = json.dumps(okFormats), expires = exp)

###################
# Database Models #
###################
class Playlist(BaseModel):
	URL = TextField(null=True)
	name = TextField()
	parent = ForeignKeyField('self', null=True, related_name='children', on_delete='SET NULL')
	justCreated = BooleanField(default=True)
	nbVids = IntegerField(default = 0)
	totNbVids = IntegerField(default = 0)
	allNbVids = IntegerField(default = 0)
	totAllNbVids = IntegerField(default = 0)
	depth = IntegerField(default = 0)

	def matchesSearch(self, searchStr):
		if searchStr.lower() in self.name.lower():
			return True
		else:
			for vid in self.videos:
				if vid.matchesSearch(searchStr):
					return True
			return False

	#def getVideosFiltered(self, searchStr):
	#	return [vid for vid in self.videos if vid.matchesSearch(searchStr)]

	def getAllVideosFiltered(self, searchStr, alphaOrdering = False):
		return [vid for vid in self.getAllVideos(alphaOrdering) if vid.matchesSearch(searchStr)]

	def addedVideos(self, nb, first = True):
		if first:
			self.nbVids += nb
		self.allNbVids += nb
		self.save()
		if self.parent:
			self.parent.addedVideos(nb, first = False)

	def addedTotVideos(self, nb, first = True):
		if first:
			self.totNbVids += nb
		self.totAllNbVids += nb
		self.save()
		if self.parent:
			self.parent.addedTotVideos(nb, first = False)

	def getAllChildren(self):
		res = [pl for pl in self.children]
		for pl in self.children:
			res += pl.getAllChildren()
		return res

	def getAllVideos(self, alphaOrdering = False):
		res = [vid for vid in self.videos]
		for ch in self.children:
			res += ch.getAllVideos()
		return sorted(res, key = lambda v: v.title) if alphaOrdering else res

	def getName(self):
		maxNb = Parameters.get().maxPlNameCharacters
		return self.name[0:maxNb] + '...' if len(self.name) > maxNb else self.name

class Video(BaseModel):
	videoId = CharField(null=True)
	origURL = TextField()
	URL = TextField(null=True)
	title = TextField()
	description = TextField(null=True)
	duration = IntegerField()
	thumbnailURL = TextField(null=True)
	playlist = ForeignKeyField(Playlist, null=True, related_name = 'videos', on_delete='CASCADE')
	infos = TextField(null=True)
	okFormatsList = TextField(null=True)
	path = TextField(null=True)
	viewed = BooleanField(default = False)
	expires = DateTimeField(null = True)
	needsInfoExtract = BooleanField(default = False)

	def getRessourcePath(self, formatId):
		if self.okFormatsList:
			ofl = json.loads(self.okFormatsList)
			return ofl[formatId]['url'] if formatId < len(ofl) else ''
		elif self.path:
			return self.path
		else:
			return ''

	def getFormat(self, formatId):
		if self.okFormatsList:
			ofl = json.loads(self.okFormatsList)
			return ofl[formatId] if formatId < len(ofl) else None
		else:
			return None

	def removeFormat(self, formatId):
		ofl = json.loads(self.okFormatsList)
		self.okFormatsList = json.dumps(ofl[0:formatId]+ofl[formatId+1:] if 0 < formatId < len(ofl) else ofl)
		self.save()

	def getFormatList(self):
		if self.okFormatsList:
			ofl = json.loads(self.okFormatsList)
			return ofl
		else:
			return {}

	def getDescription(self):
		return Markup(self.description)

	def getThumbnail(self):
		return self.thumbnailURL if self.thumbnailURL else 'static/img/NoImg.png'

	def matchesSearch(self, searchStr):
		return searchStr.lower() in self.title.lower()

	def getDurationStr(self):
		tot = self.duration
		res = ''
		res = str(tot % 60).zfill(2) + res
		tot //= 60
		if tot > 0:
			res = str(tot % 60).zfill(2) + ':' + res
			tot //= 60
			if tot > 0:
				res = str(tot) + ':' + res
		return res

class Parameters(BaseModel):
	ytUsername = TextField(null=True)
	ytPassword = TextField(null=True)
	cookiesPath = TextField(null=True)
	extensions = TextField(null=True)
	defaultPlaylist = ForeignKeyField(Playlist, null=True)
	backgroundSleepTime = DoubleField(default = 1.0)
	viewedThreshold = DoubleField(default = 0.8)
	maxPlNameCharacters = IntegerField(default = 20)
	thumbnailOffset = DoubleField(default = 0.25)
	extractInfoTimeOut = DoubleField(default = 15.0)
	dbIdTag = IntegerField()

#####################################
# Create tables if they don't exist #
#####################################
db.create_tables([Parameters, Playlist, Video], safe=True)
## TMP
if Playlist.select().count() == 0:
	pl = Playlist.create(URL = '', name = 'Default Playlist', justCreated = False)
if Parameters.select().count() == 0:
	Parameters.create(ytUsername = 'johnsmith652938@gmail.com', ytPassword='EED9PlMtBnDamJ6', cookiesPath = 'cookies.txt', extensions = 'mkv avi mpg mp4 mpeg', defaultPlaylist = pl, dbIdTag = int(time()))

