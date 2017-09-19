
var gPosition = 0;
var gDuration = 1;
var gPlaying = false;
var gPaused = false;
var gPlaylistChangeHash = 0;
var gUpdateHashes = {video:'-1', playlist:'-1', ressources:'-1'};
var gSearchTimeout = null;
var gUpdateDataInterval = null;
var gRotateTimers = {}

function displayError(text) {
	$('.ErrorBar').text(text);
}

function updatePlayPauseButtons(playing) {
	gPlaying = playing
	if (playing) {
		$('.PauseButton').css('display', 'inline-block');
		$('.PlayButton').css('display', 'none');
	} else {
		$('.PlayButton').css('display', 'inline-block');
		$('.PauseButton').css('display', 'none');
	}
}

function updateStopButton(playing) {
	if (playing) {
		$('.StopButton').css('-webkit-filter', 'none');
	} else {
		$('.StopButton').css('-webkit-filter', 'saturate(0.2)');
	}
}

function updateProgressBar(position, duration) {
	gPosition = position;
	gDuration = duration;
	$(".ProgressPlayed#VideoPP").css('width', ''+(position / duration * 100)+"%");
	$(".ProgressBar#VideoPB span").text(getHRTime(position) + ' / ' + getHRTime(duration));
}

function updatePlaying(state, paused) {
	if (typeof(paused)==='undefined') paused = false;
	gPaused = paused;
	updatePlayPauseButtons(state);
	updateStopButton(state || paused);
}

function updateData(first) {
	$.getJSON($SCRIPT_ROOT + '/_getStatus', {updateHashes: JSON.stringify(gUpdateHashes)}, function(data) {
		updateParts(data.updatedParts);
		updatePlaying(data.Status.isPlaying, data.Status.isPaused);
		setAutoUpdate(data.Status.isPlaying || data.Status.isUpdating);
		if (gPlaying || gPaused || first) {
			updateProgressBar(data.Status.position, data.Status.duration);
		}
	});
}

function updateParts(updatedParts) {
	if (!gUpdateHashes) {
		gUpdateHashes={}
	}
	if (updatedParts) {
		$.each(updatedParts, function(partName, rendered) {
			var scrT = $('.'+partName).scrollTop();
			$('.'+partName).replaceWith(rendered.part);
			$('.'+partName).scrollTop(scrT);
			gUpdateHashes[partName] = rendered.hash;
		});
	}
}

function setLoading(part, state) {
	if (state) {
		$(part + ' .LoadingIndicator').css('z-index', '1')
	} else {
		$(part + ' .LoadingIndicator').css('z-index', '-1')
	}
}

function triggerSearch() {
	setLoading('#SearchDiag', true);
	setLoading('.ressources', true);
	sendOrder('search', {searchString: $('#searchString').val()}, {anyway: function(d){setLoading('#SearchDiag', false);setLoading('.ressources', false);}, ok:function(d){}}, function(d) { return "No Items match the search." });
}

// Generic function to send orders to the application, resultCallBacks must contain {anyway:functAnyway, ok: functOk}
function sendOrder(orderName, params, resultCallBacks, ErrorFunct) {
	$.getJSON($SCRIPT_ROOT + '/_sendOrder', Object.assign({order: orderName, updateHashes: JSON.stringify(gUpdateHashes)}, params), function(data) {
		resultCallBacks.anyway(data)
		updateParts(data.updatedParts);
		if (data.result) {
			resultCallBacks.ok(data);
		} else {
			displayError(ErrorFunct(data));
		}
	});
}

function pad(n, width, z) {
	z = z || '0';
	n = n + '';
	return n.length >= width ? n : new Array(width - n.length + 1).join(z) + n;
}

function getHRTime(totSec) {
	var sec = Math.round(totSec % 60);
	totSec = Math.floor(totSec / 60);
	var min = totSec % 60;
	totSec = Math.floor(totSec / 60);
	if (totSec > 0) {
		return totSec + ':' + pad(min,2) + ':' + pad(sec,2);
	} else {
		return min + ':' + pad(sec,2);
	}
}

function hideOnClickoutAction(e, select) {
	select.slideDown("slow", function() {}); 
	$('.HideOnClickoutDialog').each( function(i, elem) {
		if (!select.is($(elem))) {
			$(elem).slideUp("slow", function() {}); 
		}
	});
	e.stopPropagation();
}

function setAutoUpdate(state) {
	if (gUpdateDataInterval && !state) {
		clearInterval(gUpdateDataInterval);
		gUpdateDataInterval = null;
	} else if (!gUpdateDataInterval && state) {
		gUpdateDataInterval = setInterval(function(){updateData(false)}, 1000);
	}
}

function setRotateTimer(elemId, state) {
	if (!state) {
		clearInterval(gRotateTimers[elemId]['timer']);
		gRotateTimers[elemId] = null;
	} else {
		gRotateTimers[elemId] = {}
		gRotateTimers[elemId]['timer'] = setInterval(function(){rotateTimer(elemId)}, 50);
		gRotateTimers[elemId]['angle'] = 0;
	}
}

function rotateTimer(elemId) {
	gRotateTimers[elemId]['angle'] += 15;
	$('.RefreshButton#'+elemId).css('transform', 'rotate(' + gRotateTimers[elemId]['angle'] + 'deg)');
}

updateData(true);
//gUpdateDataInterval = setInterval(function(){updateData(false)}, 1000);


$(function() {
	$(document).on('click', '.ProgressBar#VideoPB', function(e) {
		var posX = $(this).offset().left;
		var wdth = $(this).width();
		setLoading('.Thumbnail', true);
		updateProgressBar((e.pageX - posX)/wdth*gDuration, gDuration);
		setAutoUpdate(false)
		sendOrder('changePos', {relPos: (e.pageX - posX)/wdth}, {
			anyway: function(d){
				updateProgressBar(d.position, d.duration);
				updatePlaying(d.isPlaying, d.isPaused);
				setAutoUpdate(d.isPlaying);
				setLoading('.Thumbnail', false);
			}, 
			ok: function(d){}}, function(d){return "Couldn't jump to the specified point.";});
	});
	$(document).on('click', '.PlayButton', function(e) {
		updatePlaying(true);
		setLoading('.Thumbnail', true);
		sendOrder('play', {}, {
			anyway: function(d){
				updatePlaying(d.result);
				setLoading('.Thumbnail', false);
			}, 
			ok: function(d){
				setAutoUpdate(true);
		}}, function(d){return "Couldn't play.";});
	});
	$(document).on('click', '.PauseButton', function(e) {
		updatePlaying(false, true);
		setLoading('.Thumbnail', true);
		sendOrder('pause', {}, {
			anyway: function(d){
				updatePlaying(!d.result, d.result);
				setLoading('.Thumbnail', false);
			}, 
			ok: function(d){
				setAutoUpdate(false);
		}}, function(d){return "Couldn't pause.";});
	});
	$(document).on('click', '.StopButton', function(e) {
		if (gPlaying) {
			setLoading('.Thumbnail', true);
			updatePlaying(false);
			updateProgressBar(0, gDuration);
			sendOrder('stop', {}, {
				anyway: function(d){
					updatePlaying(!d.result);
					setLoading('.Thumbnail', false);
				}, 
				ok: function(d){
					setAutoUpdate(false);
			}}, function(d){return "Couldn't stop.";});
		}
	});
	$(document).on('change', '.Selector', function() {
		var type = $(this).attr('id');
		var newFormat = $('.Selector#' + type + ' option:selected').text();
		setLoading('.Thumbnail', true);
		sendOrder('changeFormat', {formatType: type, formatId: $(this).val()}, {
			anyway: function(d){
				setLoading('.Thumbnail', false);
			}, 
			ok: function(d){}}, 
			function(d){return "Couldn't change the " + type + " format to " + newFormat + ".";});
	});
	$(document).on('change', '#alphaOrderChkbx', function() {
		var alphaOrdr = $(this).is(":checked")
		setLoading('.playlist', true);
		sendOrder('changeOrdering', {alphaOrdering: alphaOrdr}, {anyway: function(d){
				setLoading('.playlist', false);
			}, ok: function(d){}},
			function(d){return "Couldn't change the ordering.";});
	});
	$(document).on('mouseenter', '.ProgressBar#VideoPB', function(e) {$('.ProgressBarTooltip').css('display', 'inline-block');});
	$(document).on('mouseleave', '.ProgressBar#VideoPB', function(e) {$('.ProgressBarTooltip').css('display', 'none');});
	$(document).on('mousemove', '.ProgressBar#VideoPB', function(e) {
		var posX = $(this).offset().left;
		var wdth = $(this).width();
		$('.ProgressBarTooltip').text(getHRTime(((e.pageX - posX)/wdth)*gDuration));
		$('.ProgressBarTooltip').css('left', e.pageX-posX-$('.ProgressBarTooltip').width()/2 + 'px');
	});
	$(document).on('click', '.RessourceLink', function() {
		setLoading('.ressources', true);
		setLoading('.playlist', true);
		sendOrder('selectRessource', {ressourceId: $(this).attr('value')}, {anyway: function(d){
			setLoading('.ressources', false);
			setLoading('.playlist', false);
		}, ok:function(d){}}, function(d){return "Couldn't select playlist " + $(this).text() + ".";});
	});
	$(document).on('click', '.PlaylistVidButton', function() {
		setLoading('.video', true);
		sendOrder('loadVideo', {videoId: $(this).attr('value')}, {anyway: function(d){
			setLoading('.video', false);
		}, ok:function(d){updateStopButton(gPlaying);}}, function(d){return "Couldn't load video " + $(this).attr('title') + ".";});
	});
	$(document).on('click', '#RessourceAddBtn', function() {
		setLoading('#AddRessourceDiag', true);
		setAutoUpdate(true);
		sendOrder('processURL', {urlPath: $('#ressourceUrlPath').val(), name:$('#ressourceName').val()}, {anyway: function(d){
			setLoading('#AddRessourceDiag', false);
			$('#AddRessourceDiag').slideUp("slow", function() {}); 
			$('#ressourceName').val('');
			$('#ressourceUrlPath').val('');
		}, ok:function(d){
		}}, function(d){return "Couldn't load ressource " + $('#ressourceName').val() + ".";});
	});
	$('#InterfaceAddBtn').on('mouseup', function(e) { hideOnClickoutAction(e, $('#AddRessourceDiag')); });
	$('#InterfaceSearchBtn').on('mouseup', function(e) { hideOnClickoutAction(e, $('#SearchDiag'));
	});
	$(document).on('mouseup', function(e) {
		$('.HideOnClickoutDialog').each( function(i, elem) {
			if (!$(e.target).is($(elem)) && $(e.target).closest($(elem)).length == 0) {
				$(elem).slideUp("slow", function() {}); 
			}
		});
	});
	$('#searchString').keypress(function (e) {
		$('#SearchDiag').toggleClass('HideOnClickoutDialog', $(this).val().length == 0)
		if(e.which == 13) {
			triggerSearch();
		} else {
			if ( gSearchTimeout ) {
				clearTimeout(gSearchTimeout);
			}
			gSearchTimeout = setTimeout(triggerSearch, 1000)
		}
	});
	$(document).on('click', '.RefreshButton', function(e) {
		e.stopPropagation();
		elemId = $(this).attr('id');
		setRotateTimer(elemId, true);
		setAutoUpdate(true);
		sendOrder('refreshRessource', {ressourceId: $(this).attr('id')}, {anyway: function(d){
			setRotateTimer(elemId, false);
		}, ok:function(d){}}, function(d){return "Couldn't refresh ressource.";});
	});

	$('.RessourceWrapper').resizable({
		handles: 'e',
		minWidth: 100,
		stop:function(event, ui) {
			ui.element.width(((ui.element.width()/ui.element.parent().width())*100)+'%');
		}
	});
	$('.videoWrapperInner').resizable({
		handles: 's',
		minHeight: 100,
		stop:function(event, ui) {
			ui.element.height(((ui.element.height()/ui.element.parent().parent().height())*100)+'%');
		}
	});
});
