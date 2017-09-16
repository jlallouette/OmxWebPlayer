from jinja2 import Environment, FileSystemLoader
import threading

from player import *


#def updatePlaylists(lock, appli):
#	while True:
#		with lock:
#			playlists = [pl for pl in Playlist.select().where(~(Playlist.justCreated) & Playlist.parent.is_null())]
#		for pl in playlists:
#			print('Updating playlist:', pl.URL)
#			ProcessPathURL(pl.URL, pl.name, pl = pl, changeCallBack = lambda x:appli.playlistUpdated(x), lock=lock, slow = True)
#		# TODO Set this as a parameter
#			sleep(5)
#		sleep(5)

class UpdateData:
	def __init__(self, temp, hsh):
		self.updateHash = hsh
		self.template = temp

class Application:
	def __init__(self):
		self.currPlaylist = None
		self.player = Player()

		self.searchFilterStr = ''
		self.nbUpdating = 0

		self.threadLock = threading.RLock()

		# Updating separate part of the app
		env = Environment(loader=FileSystemLoader(['templates', 'static/css']))
		self.updateData = {p:UpdateData(env.get_template(p+'.html'),0) for p in ['playlist', 'video', 'ressources']}

		# Launch the playlist updater thread
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

	def setFormat(self, formatId):
		self.updatePart('video')
		return self.player.setFormat(formatId)

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
			print('Refreshing playlist ' + pl.name)
			ret = ProcessPathURL(pl.URL, pl.name, changeCallBack = self.playlistUpdated, lock=self.threadLock)
			self.updatePart('ressources')
			self.nbUpdating -= 1;
			return ret is not None
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
		print('callback!')

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
					curRoot = [pl for pl in self.currPlaylist.children] + [self.currPlaylist]
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

