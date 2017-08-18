import subprocess
from multiprocessing import Queue
import json
import datetime
import re
from time import sleep
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
		return ProcessYoutubeURL(urlPath, name, pl, changeCallBack, lock)
	else:
		return ProcessPath(urlPath, name, pl, changeCallBack, lock, slow = slow)

# Scans a path and adds all the videos to the database
# Creates a new playlist for each non empty subfolder 
def ProcessPath(path, name, pl = None, changeCallBack = None, lock = None, firstCall=True, slow = False):
	with lock:
		extRe=re.compile('(.*?)\.(' + '|'.join(Parameters.get().extensions.split()) + ')$')
		defaultPl = Parameters.get().defaultPlaylist
		sleepTime = Parameters.get().backgroundSleepTime
	allPl = []
	for dirpath, dirNames, fileNames in os.walk(path):
		vidFileMatch = list(filter(lambda x: x, map(extRe.match, fileNames)))
		if len(vidFileMatch) + len(dirNames) > 0:

			with lock:
				if Playlist.select().where(Playlist.URL == dirpath).count() == 0:
					currPl = Playlist.create(URL = dirpath, name = os.path.basename(dirpath) if pl else name, parent = pl, totNbVids = len(vidFileMatch), depth = pl.depth + 1 if pl else 0)
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
					# TODO Check ffprobe or some related stuff to get info about videos
					dur = 10
					res = 'blaxbli'
					okFormats = {-1: {'name':res, 'url':vidPath}}
					with lock:
						Video.create(origURL = vidPath, path = vidPath, title = vfm.group(1), duration=dur, playlist = currPl, okFormatsList = json.dumps(okFormats))
						currPl.nbVids += 1
						currPl.save()
					changeCallBack(currPl)
				if slow:
					sleep(sleepTime)

			# Remove deleted or unaccessible videos
			with lock:
				nbOrphans = Video.select().where((Video.playlist == currPl) & ~(Video.path << allVidPaths)).count()
				if nbOrphans > 0:
					Video.delete().where((Video.playlist == currPl) & ~(Video.path << allVidPaths)).execute()
					currPl.totNbVids -= nbOrphans
					currPl.nbVids = currPl.totNbVids
					currPl.save()
					changeCallBack(currPl)

			# Add subdirectories
			for dirn in dirNames:
				allPl += ProcessPath(os.path.join(path, dirn), name, currPl, changeCallBack, lock, firstCall=False, slow = slow) 

			# Delete empty playlists
			with lock:
				if currPl.getTotalNbVids() == 0:
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
def InsertYtPlaylist(infos, url, name, existPl = None, changeCallBack=None, lock = None):#, progressQueue = None):
	with lock:
		if existPl:
			pl = existPl
			pl.totNbVids = len(infos)
			pl.save()
		else:
			pl = Playlist.create(URL = url, name = name, totNbVids = len(infos))
	changeCallBack(pl)

	changed = False
	for info in infos:
		with lock:
			vidDidntExist = (Video.select().where(Video.origURL == info['url']).count() == 0)
			changed = changed or vidDidntExist
			vid = None if vidDidntExist else Video.get(Video.origURL == info['url'])
		ret = ProcessYoutubeURL(info['url'], '', pl, changeCallBack, lock, vid)#, progressQueue)
		if vidDidntExist:
			with lock:
				pl.nbVids += 1
				pl.save()
		changeCallBack(pl)

	# Remove videos that were deleted from the playlist
	if existPl:
		allUrls = [info['url'] for info in infos]
		with lock:
			if Video.select().where((Video.playlist == existPl) & ~(Video.origURL << allUrls)).count() > 0:
				changed = True
				Video.delete().where((Video.playlist == existPl) & ~(Video.origURL << allUrls)).execute()
		# If the playlist was changed, mark it as changed
		if changed and changeCallBack:
			with lock:
				pl.nbVids = pl.totNbVids
				pl.save()
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
	p = re.compile('.*[^0-9]+(\d+x\d+).*');
	okFormats = {f['format_id']: {'name':p.match(f['format']).group(1),'url':f['url']}  for f in infos['formats'] if ('only' not in f['format']) and ('video' not in f['format'])}
	okFormats[-1] = {'name':'Auto', 'url':''}
	# Expiration time for the streams
	p2 = re.compile('.*expire=(\d+)&.*')
	exp = None
	if len(okFormats) > 0:
		for fid, f in okFormats.items():
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
	depth = IntegerField(default = 0)

	def matchesSearch(self, searchStr):
		if searchStr.lower() in self.name.lower():
			return True
		else:
			for vid in self.videos:
				if vid.matchesSearch(searchStr):
					return True
			return False

	def getVideosFiltered(self, searchStr):
		return [vid for vid in self.videos if vid.matchesSearch(searchStr)]

	def getAllVideosFiltered(self, searchStr):
		return [vid for vid in self.getAllVideos() if vid.matchesSearch(searchStr)]

	def getNbVids(self):
		return self.nbVids + sum([c.getNbVids() for c in self.children])

	def getTotalNbVids(self):
		return self.totNbVids + sum([c.getTotalNbVids() for c in self.children])

	def getAllChildren(self):
		res = [pl for pl in self.children]
		for pl in self.children:
			res += pl.getAllChildren()
		return res

	def getAllVideos(self):
		res = [vid for vid in self.videos]
		for ch in self.children:
			res += ch.getAllVideos()
		return res

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

	def getRessourcePath(self, formatId):
		if self.okFormatsList:
			ofl = json.loads(self.okFormatsList)
			return ofl[formatId]['url'] if formatId in ofl else ''
		elif self.path:
			return self.path
		else:
			return ''

	def getFormat(self, formatId):
		if self.okFormatsList:
			ofl = json.loads(self.okFormatsList)
			return ofl[formatId] if formatId in ofl else None
		else:
			return None

	def removeFormat(self, formatId):
		self.okFormatsList = json.dumps({fid: elems for fid, elems in json.loads(self.okFormatsList).items() if fid != formatId})
		self.save()

	def getFormatList(self):
		if self.okFormatsList:
			ofl = json.loads(self.okFormatsList)
			return {ft['name']:fid for fid, ft in ofl.items()}
		else:
			return None

	def getDescription(self):
		return Markup(self.description)

	def getThumbnail(self):
		return self.thumbnailURL if self.thumbnailURL else 'static/img/NoImg.png'

	def matchesSearch(self, searchStr):
		return searchStr.lower() in self.title.lower()

class Parameters(BaseModel):
	ytUsername = TextField(null=True)
	ytPassword = TextField(null=True)
	cookiesPath = TextField(null=True)
	extensions = TextField(null=True)
	defaultPlaylist = ForeignKeyField(Playlist, null=True)
	backgroundSleepTime = DoubleField(default = 1.0)

#####################################
# Create tables if they don't exist #
#####################################
db.create_tables([Parameters, Playlist, Video], safe=True)
## TMP
if Playlist.select().count() == 0:
	pl = Playlist.create(URL = '', name = 'Default Playlist')
if Parameters.select().count() == 0:
	Parameters.create(ytUsername = 'johnsmith652938@gmail.com', ytPassword='EED9PlMtBnDamJ6', cookiesPath = 'cookies.txt', extensions = 'mkv avi mpg mp4 mpeg', defaultPlaylist = pl)

