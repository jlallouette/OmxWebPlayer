#import subprocess
from omxplayer import OMXPlayer
import copy
from time import sleep

from video import *

class Player:
	def __init__(self):
		self.currVideo = None
		self.formatId = -1
		self.omxProcess = None
	
	def LoadVideo(self, video):
		if self.isStarted():
			self.stop()
		self.currVideo = video

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
				if self.isPlaying():
					self.omxProcess.pause()
				else:
					self.omxProcess.play()
				return True
			else:
				ok = False
				if self.formatId != -1:
					ok = self.tryPlayingFormat(self.formatId)
				if not ok:
					# Try to play formats starting from the highest resolution one
					# TODO sort by resolution
					for name, fid in self.currVideo.getFormatList().items():
						if fid != -1 and self.tryPlayingFormat(fid):
							ok = True
							break
				return ok
		return False

	def stop(self):
		if self.omxProcess:
			self.omxProcess.quit()
			self.omxProcess = None
			return True
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
			self.isPlaying()
			sleep(2)
			if self.isPlaying():
				print('isplaying:True')
				return True
		except Exception as e:
			print(str(e), str(self.currVideo.getFormatList()))
		# Handle the case in which the format couldn't be played
		self.currVideo.removeFormat(formatId)
		self.stop()
		self.formatId = -1
		return False


	def isPlaying(self):
		return self.omxProcess and self.omxProcess.is_playing()

	def isStarted(self):
		return self.omxProcess and self.omxProcess.can_play()

	def getPosition(self):
		if self.isStarted():
			return self.omxProcess.position()
		else:
			return 0
			
	def getDuration(self):
		if self.isStarted():
			return int(self.omxProcess.duration())
		elif self.currVideo:
			return self.currVideo.duration
		else:
			return 1

	def getStatus(self):
		return {'position':self.getPosition(), 'duration':self.getDuration(), 'isPlaying':self.isPlaying(), 'formatList':self.getFormatList()}

	def setPosition(self, newPos):
		# If the video is not started, start it and jump to the position
		if self.isStarted() or self.playPause():
			self.omxProcess.set_position(newPos)
			return True
		else:
			return False

	def getFormatList(self):
		return self.currVideo.getFormatList() if self.currVideo else {}

	def getFormatListItems(self):
		if self.currVideo:
			fl = self.currVideo.getFormatList()
			return fl.items() if fl else []
		else:
			return []

