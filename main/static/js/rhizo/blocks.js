// Blocks are the basis of apps. A user can put together a combination of blocks
// to create a new app (ideally without any programming).


// ======== block management ========


// a subset of blocks that are interactive or update with live server data
var g_liveBlocks = {};


// creates a block DOM elements and code given a list of block specifications;
// returns a jQuery DOM element containing all the blocks
function createBlocks(blockSpecs) {
	var container = $('<div>');
	for (var i = 0; i < blockSpecs.length; i++) {
		createBlock(blockSpecs[i]).appendTo(container);
	}
	return container;
}


// fix(clean): combine this with createBlocks?
function readyBlocks() {
	$.each(g_liveBlocks, function(id, block) {
		if (block.onready) {
			block.onready();
		}
	});
}


// create a block from a JSON specification of the block;
// for live/interactive blocks, creates a block object/instance and stores in g_liveBlocks;
// returns jQuery DOM element;
function createBlock(blockSpec) {
	var blockElem = null;
	switch (blockSpec.type) {

	// heading block
	case 'heading':
		blockElem = $('<h3>', {html: blockSpec.text});
		break;

	// horizontal group block
	case 'hgroup':
		blockElem = createBlocks(blockSpec.blocks);
		blockElem.addClass('hgroup');
		break;

	// simple div block (for custom use)
	case 'div':
		blockElem = $('<div>', {id: blockSpec.id});
		break;

	// button block
	case 'button':
		blockElem = $('<button>', {class: 'btn block', onclick: blockSpec.onclick, html: blockSpec.text});
		if (blockSpec.primary) {
			blockElem.addClass('btn-primary');
		} else {
			blockElem.addClass('btn-default');
		}
		break;

	// text input block
	case 'textInput':
		var label = blockSpec.label || generateLabel(blockSpec.name);
		blockElem = $('<div>', {class: 'sequenceBlock'});
		$('<div>', {class: 'sequenceLabel', html: label}).appendTo(blockElem);
		if (!blockSpec.id) {
			blockSpec.id = blockSpec.name;
		}
		createTextInput(blockSpec).appendTo(blockElem);
		break;

	// selection block
	case 'selector':
		var label = blockSpec.label || generateLabel(blockSpec.name);
		blockElem = $('<div>', {class: 'sequenceBlock'});
		$('<div>', {class: 'sequenceLabel', html: label}).appendTo(blockElem);  // fix(later): generalize; don't use sequenceLabel class
		if (!blockSpec.id) {
			blockSpec.id = blockSpec.name;
		}
		createSelector(blockSpec).appendTo(blockElem);
		break;

	// live sequence block
	case 'sequence':
		var name = blockSpec.name;
		var label = blockSpec.label || generateLabel(blockSpec.name);

		// prepare block object
		var block = {
			id: name,
			sequenceName: g_sequencePrefix + '/' + name, // fix(soon): we're assuming this global are set
			folderPath: g_sequencePrefix,  // fix(clean): could remove this and compute from sequenceName
		};

		// create DOM element and init block class
		if (blockSpec.view == 'large') {// fix(soon): rethink view modes
			var name = blockSpec.name;
			blockElem = $('<div>');
			$('<h3>', {html: label}).appendTo(blockElem);
			$('<div>', {id: blockSpec.name}).appendTo(blockElem);
			initLog(block);
		} else if (blockSpec.view == 'image') {
			blockElem = $('<div>', {id: blockSpec.name, class: 'imageSequence'});
			$('<img>', {id: blockSpec.name + '_img'}).appendTo(blockElem);
			initImageSequence(block);
		} else {
			blockElem = $('<div>', {class: 'sequenceBlock'});
			$('<div>', {class: 'sequenceLabel', html: label}).appendTo(blockElem);
			$('<div>', {class: 'sequenceValue', id: blockSpec.name, html: '...'}).appendTo(blockElem);
			initSequence(block);
		}

		// store in collection of blocks
		g_liveBlocks[name] = block;
		break;
	}
	return blockElem;
}


// generate a label from a block name by converting underscores/camelCase to title case
// fix(later): could handle camel case and underscores separately
function generateLabel(blockName) {
	var label = blockName.replace('_', ' ');
	return titleCase(splitCamelCase(label));
}


// ======== block classes ========


// init a block object for displaying updates to a general-purpose sequence
function initSequence(block) {

	// fix(clean): remove?
	block.onready = function() {
		connectWebSocket();
	}

	// handle an update message for this sequence
	block.onValue = function(timestamp, value) {
		if (this.format && this.dataType === 1) {
			var decimalPlaces = parseInt(this.format);
			value = value.toFixed(decimalPlaces);
		}
		$('#' + this.id).html(value);
	}

	// make sure we receive updates for this sequence
	subscribeToFolder(block.folderPath);
}


// init a block object for displaying updates to a log sequence
function initLog(block) {
	block.nextLogEntryIndex = 0;
	block.entries = [];

	// fix(clean): remove?
	block.onready = function() {
		$.each(this.entries, function(index, value) {
			console.log('initLog:' + value);
			block.onValue(value[0], value[1]);
		});
		connectWebSocket();
	}

	// handle an update message for this sequence
	block.onValue = function(timestamp, value) {
		var logEntryDiv = $('<div/>', {id: this.id + '_' + this.nextLogEntryIndex});
		this.nextLogEntryIndex++;
		var timeStr = moment(timestamp).format('YYYY-M-DD H:mm:ss');
		$('<span/>', {html: timeStr, class: 'logTimestamp'}).appendTo(logEntryDiv);
		$('<span/>', {html: value, class: 'logText'}).appendTo(logEntryDiv);
		logEntryDiv.prependTo($('#' + this.id));
		var maxCount = 50;
		if (this.nextLogEntryIndex > maxCount) {
			var removeIndex = this.nextLogEntryIndex - maxCount - 1;
			$('#' + this.id + '_' + removeIndex).remove();
		}
	}

	// make sure we receive updates for this sequence
	subscribeToFolder(block.folderPath);
}


// init a block object for displaying updates to an image sequence
function initImageSequence(block) {

	// fix(clean): remove?
	block.onready = function() {
		connectWebSocket();
	}

	// handle an update message for this sequence
	block.onValue = function(timestamp, value) {
//		console.log('block: ' + this.id);
//		console.log('image: ' + value);
		var resourceName = this.sequenceName;  // we assume the sequence name has a leading slash
		var d = new Date();
		$('#' + this.id + '_img').attr('src', '/api/v1/resources' + resourceName + '?' + d.getTime());  // add time to prevent caching
	}

	// make sure we receive updates for this sequence
	subscribeToFolder(block.folderPath);
}
