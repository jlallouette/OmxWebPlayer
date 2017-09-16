#import subprocess
from omxplayer import OMXPlayer
import copy

from video import *

class Player:
	def __init__(self):
		self.currVideo = None
		self.formatId = 0
		self.omxProcess = None
	
	def LoadVideo(self, video):
		if self.isStarted():
			self.stop()
		self.currVideo = video
		self.formatId = 0

	# Set the format of the video
	def setFormat(self, formatId):
		if self.currVideo and formatId != self.formatId:
			# If the video has this format
			if self.currVideo.getFormat(formatId):
				oldFormat = self.formatId
				self.formatId = formatId
				if self.isStarted():
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
					# TODO sort by resolution
					#for name, fid in self.currVideo.getFormatList().items():
					#	if fid != 0 and self.tryPlayingFormat(fid):
					#		ok = True
					#		break
				return ok
		return False

	def stop(self):
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
		self.currVideo.removeFormat(formatId)
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

	def getStatus(self):
		return {'position':self.getPosition(), 'duration':self.getDuration(), 'isPlaying':self.isPlaying(), 'isPaused':self.isPaused()}

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

