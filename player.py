#import subprocess
from omxplayer import OMXPlayer
import copy

from video import *

class Player:
	def __init__(self, appli):
		self.currVideo = None
		self.formatId = 0
		self.subtitleId = -1
		self.audioStreamId = 0
		self.omxProcess = None
		self.currTotViewed = 0
		self.lastPos = 0
		self.appli = appli
		self.wasPlaying = False
	
	def LoadVideo(self, video):
		if self.isStarted():
			self.stop()
		self.currVideo = video
		self.formatId = 0
		self.subtitleId = -1
		self.audioStreamId = 0
		self.currTotViewed = 0
		self.lastPos = 0
		self.wasPlaying = False

	# Set the format of the video
	def setVideoFormat(self, formatId):
		if self.currVideo and formatId != self.formatId:
			# If the video has this format
			if self.currVideo.getFormat(formatId):
				oldFormat = self.formatId
				self.formatId = formatId
				if self.isStarted():
					self.wasPlaying = False
					oldPos = self.getPosition()
					wasPlaying = self.isPlaying()
					# Try to play the new format but fallback on the previous one if it fails
					if self.tryPlayingFormat(formatId) or self.tryPlayingFormat(oldFormat):
						self.setPosition(oldPos)
						if not wasPlaying:
							self.playPause()
					else:
						return False
				return True
		return False

	# Set a different audio stream
	def setAudioFormat(self, formatId):
		try:
			if self.isStarted():
				if self.omxProcess.select_audio(formatId):
					self.audioStreamId = formatId
					return True
				else:
					return False
			else:
				return False
		except:
			self.clearPlayer()
			return False

	# Set a subtitle track
	def setSubtitlesFormat(self, formatId):
		try:
			if self.isStarted():
				if formatId > -1:
					self.omxProcess.show_subtitles()
					if self.omxProcess.select_subtitle(formatId):
						self.subtitleId = formatId
						return True
					else:
						return False
				else:
					self.subtitleId = -1
					return self.omxProcess.hide_subtitles()
			else:
				return False
		except:
			self.clearPlayer()
			return False

	# Tries to play or pause the current video
	def playPause(self):
		if self.currVideo:
			if self.isStarted():
				try:
					if self.isPlaying():
						self.omxProcess.pause()
					else:
						self.omxProcess.play()
					return True
				except:
					self.clearPlayer()
					return False
			else:
				ok = False
				if self.formatId != 0:
					ok = self.tryPlayingFormat(self.formatId)
				if not ok:
					# Try to play formats starting from the highest resolution one
					for fid in range(1, len(self.currVideo.getFormatList())):
						if self.tryPlayingFormat(fid):
							ok = True
							break
				return ok
		return False

	def stop(self):
		self.wasPlaying = False
		try:
			if self.omxProcess:
				self.omxProcess.quit()
				self.omxProcess = None
				return True
			return False
		except:
			self.clearPlayer()
			return False

	# Tries to play a given format of the video
	def tryPlayingFormat(self, formatId):
		if self.isStarted():
			self.stop()
		try:
			self.formatId = formatId
			print('Trying to play ', formatId, 'path:', self.currVideo.getRessourcePath(formatId))
			self.omxProcess = OMXPlayer(self.currVideo.getRessourcePath(formatId), args=['-b'])
			# Wait a bit for loading before disqualifying the format
			while self.omxProcess.playback_status() == 'Paused':
				sleep(0.01)
			if self.isPlaying():
				print('isplaying:True')
				return True
		except Exception as e:
			self.clearPlayer()
			print(str(e), str(self.currVideo.getFormatList()))
		# Handle the case in which the format couldn't be played
		self.stop()
		self.formatId = 0
		return False


	def isPlaying(self):
		try:
			return self.omxProcess and self.omxProcess.is_playing()
		except:
			self.clearPlayer()
			return False

	def isStarted(self):
		try:
			return self.omxProcess and self.omxProcess.can_play()
		except:
			self.clearPlayer()
			return False

	def isPaused(self):
		return self.isStarted() and not self.isPlaying()

	def getPosition(self):
		try:
			if self.isStarted():
				return self.omxProcess.position()
			else:
				return 0
		except:
			self.clearPlayer()
			return 0
			
	def getDuration(self):
		try:
			if self.isStarted():
				return int(self.omxProcess.duration())
			elif self.currVideo:
				return self.currVideo.duration
			else:
				return 1
		except:
			self.clearPlayer()
			return 1

	def getSubtitles(self):
		subs = {-1: 'None'}
		try:
			if self.isStarted():
				for substr in self.omxProcess.list_subtitles():
					idx, lng, name, cdc, actv = substr.split(':')
					subs[idx] = lng + (('-' + name) if len(name) > 0 else '')
					if actv:
						self.subtitleId = idx
			return subs
		except:
			self.clearPlayer()
			return subs

	def hasSubtitles(self):
		try:
			return self.isStarted() and len(self.omxProcess.list_subtitles()) > 0
		except:
			self.clearPlayer()
			return False

	def getAudioStreams(self):
		auds = {}
		try:
			if self.isStarted():
				for audstr in self.omxProcess.list_audio():
					idx, lng, name, cdc, actv = audstr.split(':')
					auds[idx] = lng + (('-' + name) if len(name) > 0 else '')
					if actv:
						self.audioStreamId = idx
			return auds
		except:
			self.clearPlayer()
			return auds

	def hasAudioStreams(self):
		try:
			return self.isStarted() and len(self.omxProcess.list_audio()) > 1
		except:
			self.clearPlayer()
			return False

	def hasVideoStreams(self):
		if self.currVideo:
			okFormatList = json.loads(self.currVideo.okFormatsList)
			return len(okFormatList) > 2
		else:
			return False

	def getStatus(self):
		isPlaying = self.isPlaying()
		isPaused = self.isPaused()
		currPos = self.getPosition()
		dur = self.getDuration()
		if isPlaying or isPaused:
			self.wasPlaying = True
			self.currTotViewed += currPos - self.lastPos
			self.lastPos = currPos
			with self.appli.threadLock:
				if self.currTotViewed / dur > Parameters.get().viewedThreshold:
					self.currVideo.viewed = True
					self.currVideo.save()
					self.appli.updatePart('playlist')
		else:
			with self.appli.threadLock:
				pt = Parameters.get().autoRestartPosThresh
			if self.wasPlaying and pt < self.lastPos < self.getDuration() - pt:
				self.tryPlayingFormat(self.formatId)
				self.setPosition(self.lastPos)
		return {'position':currPos, 'duration':dur, 'isPlaying':isPlaying, 'isPaused':isPaused}

	def setPosition(self, newPos):
		try:
			# If the video is not started, start it and jump to the position
			if self.isStarted() or self.playPause():
				self.omxProcess.set_position(newPos)
				return True
			else:
				return False
		except:
			self.clearPlayer()
			return False

	def getFormatList(self):
		return self.currVideo.getFormatList() if self.currVideo else []

	def getFormatListItems(self):
		return [(fid, f['name']) for fid, f in enumerate(self.getFormatList())]

	def clearPlayer(self):
		if self.omxProcess:
			try:
				self.omxProcess.quit()
			except:
				pass
		self.omxProcess = None

