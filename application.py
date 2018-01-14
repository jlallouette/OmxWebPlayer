from jinja2 import Environment, FileSystemLoader
import threading
import multiprocessing
import av

from player import *

def extractInfos(vid, q, offstrt, dbIdTag):
	try:
		container = av.open(vid.path)
		timeBase = 1000000
		dur = container.duration // timeBase
		q.put(dur)
		offset = container.duration * offstrt
		container.seek(int(offset))
		frame = next(container.decode(video=0))
		res = str(frame.width) + 'x' + str(frame.height)
		q.put(res)
		thumbPath = 'static/thumbnails/' + str(dbIdTag) + '-' + str(vid.id) + '.jpg'
		frame.to_image().save(thumbPath)
		q.put(thumbPath)
	except:
		pass

def extractInfosFromFiles(lock, appli):
	while True:
		with lock:
			params = Parameters.get()
		try:
			with lock:
				vid = Video.get(Video.needsInfoExtract == True)
			print('treating vid ', vid.id, vid.path)
			# Getting duration, resolution and thumbnail from the file
			q = multiprocessing.Queue()
			functThread = multiprocessing.Process(target = extractInfos, args = (vid, q, params.thumbnailOffset, params.dbIdTag,))
			functThread.start()
			functThread.join(params.extractInfoTimeOut)
			if functThread.is_alive():
				functThread.terminate()
				print('Terminated !')
			else:
				print('Joined!')
			with lock:
				try:
					vid.duration = q.get(False)
					ofl = json.loads(vid.okFormatsList)
					ofl[1]['name'] = q.get(False)
					vid.okFormatsList = json.dumps(ofl)
					vid.thumbnailURL = q.get(False)
				except:
					pass
				vid.needsInfoExtract = False
				vid.save()
			sleep(0.5)
		except:
			sleep(1)

class UpdateData:
	def __init__(self, temp, hsh):
		self.updateHash = hsh
		self.template = temp

class Application:
	def __init__(self):
		self.currPlaylist = None
		self.player = Player(self)

		self.searchFilterStr = ''
		self.alphaOrdering = False
		self.hideViewed = False
		self.nbUpdating = 0

		self.threadLock = threading.RLock()

		# Updating separate part of the app
		env = Environment(loader=FileSystemLoader(['templates', 'static/css']))
		self.updateData = {p:UpdateData(env.get_template(p+'.html'),0) for p in ['playlist', 'video', 'ressources']}

		# Launch the playlist updater thread
		self.infoExtractThread = threading.Thread(target = extractInfosFromFiles, args = (self.threadLock, self,), daemon = True)
		self.infoExtractThread.start()
		#self.playlistUpdtThread = threading.Thread(target = updatePlaylists, args = (self.threadLock, self,))
		#self.playlistUpdtThread.daemon = True
		#self.playlistUpdtThread.start()

	def processURL(self, url, name):
		self.nbUpdating += 1
		ret = ProcessPathURL(url, name, changeCallBack = self.playlistUpdated, lock=self.threadLock)
		self.nbUpdating -= 1
		self.updatePart('ressources')
		if isinstance(ret, Video):
			return self.loadVideo(ret)
		elif isinstance(ret, Playlist):
			return self.selectPlaylist(ret)
		return False if not isinstance(ret, list) else True

	def selectPlaylist(self, plst):
		try:
			if isinstance(plst, int):
				with self.threadLock:
					plst = Playlist.get(Playlist.id == plst)
			# Determine if we need to update the ressource list
			with self.threadLock:
				if plst.children.count() > 0 or (self.currPlaylist and self.currPlaylist.children.count() > 0):
					self.updatePart('ressources')
			self.currPlaylist = plst
			self.updatePart('playlist')
			return True
		except:
			return False

	def loadVideo(self, vid):
		try:
			if isinstance(vid, int):
				with self.threadLock:
					vid = Video.get(Video.id == vid)
			if vid.expires and vid.expires <= datetime.datetime.now():
				print('Updating video: ' + vid.URL)
				ProcessYoutubeURL(vid.URL, vid.title, lock=self.threadLock, vid=vid)
			self.player.LoadVideo(vid)
			self.updatePart('video')
			return True
		except:
			return False

	def playPause(self):
		self.updatePart('video')
		return self.player.playPause()

	def goBack(self):
		with self.threadLock:
			dur = Parameters.get().arrowKeyMoveDuration
		return self.player.setPosition(self.player.getPosition() - dur)

	def goForward(self):
		with self.threadLock:
			dur = Parameters.get().arrowKeyMoveDuration
		return self.player.setPosition(self.player.getPosition() + dur)

	def setFormat(self, formatType, formatId):
		self.updatePart('video')
		if formatType == 'Video':
			return self.player.setVideoFormat(formatId)
		elif formatType == 'Audio':
			return self.player.setAudioFormat(formatId)
		elif formatType == 'Subtitles':
			return self.player.setSubtitlesFormat(formatId)
		else:
			return False

	def searchFilter(self, searchStr):
		self.searchFilterStr = searchStr
		self.updatePart('playlist')
		self.updatePart('ressources')
		return len(self.getRessources()) > 0

	def refreshRessource(self, plId):
		try:
			self.nbUpdating += 1;
			with self.threadLock:
				pl = Playlist.get(Playlist.id == plId)
			ret = ProcessPathURL(pl.URL, pl.name, changeCallBack = self.playlistUpdated, lock=self.threadLock)
			self.updatePart('ressources')
			self.nbUpdating -= 1;
			return True
		except:
			self.nbUpdating -= 1;
			return False

	def getStatus(self):
		status = self.player.getStatus()
		status['isUpdating'] = self.nbUpdating > 0
		return status

	def playlistUpdated(self, pl):
		if self.currPlaylist and pl.id == self.currPlaylist.id:
			self.updatePart('playlist')
		self.updatePart('ressources')

	# Signals a change in a part of the application
	def updatePart(self, name):
		if name in self.updateData:
			self.updateData[name].updateHash += 1

	# Returns all the ressources
	def getRessources(self):
		if not self.searchFilterStr:
			with self.threadLock:
				roots = [pl for pl in Playlist.select().where(Playlist.parent.is_null())]
				curRoot = []
				if self.currPlaylist:
					curPl = Playlist.get(Playlist.id == self.currPlaylist.id)
					curRoot = [pl for pl in curPl.children] + [curPl]
					while curRoot[-1].parent:
						curRoot.append(curRoot[-1].parent)
			res = []
			for pl in roots:
				if self.currPlaylist and (pl.id == curRoot[-1].id):
					res += curRoot[::-1]
				else:
					res.append(pl)
			return res
		else:
			return [pl for pl in Playlist.select() if pl.matchesSearch(self.searchFilterStr)]

	# Renders a part of the application using the appropriate template
	def renderPart(self, name):
		with self.threadLock:
			return Markup(self.updateData[name].template.render(appli=self)) if name in self.updateData else ''

	# Re-renders parts that have changed
	def getUpdatedParts(self, oldHashes):
		updatedParts={}
		for part, updtData in self.updateData.items():
			if part in oldHashes and updtData.updateHash != int(oldHashes[part]):
				updatedParts[part] = {'hash':updtData.updateHash, 'part':self.renderPart(part)}
		return updatedParts

	# Returns a default name for an additional ressource
	def getDefaultRessourceName(self):
		nbpl = 0
		with self.threadLock:
			nbpl = Playlist.select().count()
		return 'Ressource_' + str(nbpl + 1)

	# Sets whether he videos in the playlist are ordered alphabetically
	def setOrdering(self, alphaOrdr):
		self.alphaOrdering = alphaOrdr
		self.updatePart('playlist')
		return True

	# Set whether viewed videos are displayed
	def setHideViewed(self, hideVwd):
		self.hideViewed = hideVwd
		self.updatePart('playlist')
		return True

	def getParametersList(self):
		with self.threadLock:
			return Parameters.get().getAdjustableParameters()

	def setParameters(self, params):
		ok = True
		for cat, lst in self.getParametersList().items():
			for item in lst:
				with self.threadLock:
					ok = ok and item.setValue(params.get(item.name, '', type=str))
					if not ok:
						break
		return ok

