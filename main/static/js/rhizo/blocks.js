// Blocks are the basis of apps. A user can put together a combination of blocks
// to create a new app (ideally without any programming).


// ======== block management ========


// a subset of blocks that are interactive or update with live server data
var g_liveBlocks = {};
var g_addedSeqHandler = false;


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


// register sequence_update handler (if not already done)
function addSequenceHandler() {
	if (g_addedSeqHandler === false) {
		g_wsh.addHandler('sequence_update', function(timestamp, params) {
			//console.log('sequence: ' + params['name'] + ', value: ' + params['value']);
			var sequencePath = params['name'];  // full/absolute path of sequence
			$.each(g_liveBlocks, function(id, block) {
				var seqPaths = block.sequencePaths;
				for (var i = 0; i < seqPaths.length; i++) {
					if (seqPaths[i] === sequencePath) {
						// fix(soon): should use params['timestamp']? (not defined if from arduino)
						block.onValue(sequencePath, timestamp, params['value']);
					}
				}
			});
		});
		g_addedSeqHandler = true;
	}
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
		var fullSeqPath = g_sequencePrefix + '/' + name;

		// prepare block object
		var block = {
			id: name.split('/').join('_'),  // fix(clean): use replace function instead?
			sequencePaths: [fullSeqPath], 
		};

		// create DOM element and init block class
		if (blockSpec.view == 'large') {// fix(soon): rethink view modes
			blockElem = $('<div>');
			$('<h3>', {html: label}).appendTo(blockElem);
			$('<div>', {id: block.id}).appendTo(blockElem);
			initLog(block);
		} else if (blockSpec.view == 'image') {
			blockElem = $('<div>', {id: block.id, class: 'imageSequence'});
			$('<img>', {id: block.id + '_img'}).appendTo(blockElem);
			initImageSequence(block);
		} else {
			blockElem = $('<div>', {class: 'sequenceBlock'});
			$('<div>', {class: 'sequenceLabel', html: label}).appendTo(blockElem);
			$('<div>', {class: 'sequenceValue', id: block.id, html: '...'}).appendTo(blockElem);
			initSequence(block);
		}

		// make sure we receive updates for this sequence
		subscribeToFolder(fullSeqPath.substr(0, fullSeqPath.lastIndexOf('/')));
		addSequenceHandler();

		// store in collection of blocks
		g_liveBlocks[name] = block;
		break;

	case 'plot':
		var name = blockSpec.name;
		var id = name.split('/').join('_');  // fix(clean): use replace function instead?
		var relSeqPaths = blockSpec.sequences;
		var width = 700;
		var height = 200;
		var seqPaths = [];
		for (var i = 0; i < relSeqPaths.length; i++) {
			seqPaths.push(g_sequencePrefix + '/' + relSeqPaths[i]);
		}

		blockElem = $('<div>');
		$('<canvas>', {id: id + '_canvas', width: width, height: height}).appendTo(blockElem);
		//$('<br>').appendTo(blockElem);
		//$('<button>', {class: 'btn', html: 'Zoom In'}).appendTo(blockElem);  // plotHandler.zoomIn()
		//$('<button>', {class: 'btn', html: 'Zoom Out'}).appendTo(blockElem);

		// prepare block object
		var block = {
			id: id,
			sequencePaths: seqPaths,
			width: width,
			height: height,
		};
		initPlot(block, blockSpec);

		// store in collection of blocks
		g_liveBlocks[name] = block;
		break;

	// rhizotron bin selecton block
	case 'rhizo_bin':
		// Main div
		blockElem = $('<div>', {class: 'rhizo_binBlock col-md-3', style: 'padding-left: 0px; padding-bottom: 15px;'});
		blockElem.attr('value', blockSpec.value);

		// The split-button
		split_button = $('<div>', {class: 'btn-group', style:'margin-bottom: 0px; width: 100%;' });
		// split-button main button
		split_left = $('<button>', {class: 'btn btn-primary', type: 'button', title: 'Process all enabled rhizotrons.',
										onclick: 'processRhizotronBin(this,0)', html: blockSpec.text, style: 'width: calc(100% - 26px);'});
		// split-button drop-down button
		split_right = $('<button>', {class: 'btn btn-primary dropdown-toggle', type: 'button', style: 'width:26px;'});
		split_right.attr('data-toggle', 'dropdown');
		split_right.attr('aria-expanded', 'false');
		$('<span>', {class: 'caret'}).appendTo(split_right);

		// split-button drop-down menu
		split_menu = $('<ul>', {class: 'dropdown-menu', role: 'menu', style: 'right: 0px; left:auto;'});
		split_menu_item_1 = $('<li>', {html: '<a href="#" onclick="enableAllRhizotrons(this)">Enable All</a>'});
		split_menu_item_1.appendTo(split_menu);
		split_menu_item_2 = $('<li>', {html: '<a href="#" onclick="disableAllRhizotrons(this)">Disable All</a>'});
		split_menu_item_2.appendTo(split_menu);
		split_menu_divider = $('<li>', {html: '<div class="dropdown-divider"></div>'});
		split_menu_divider.appendTo(split_menu);
			
		// Add left and right parts and the menu
		split_left.appendTo(split_button);
		split_right.appendTo(split_button);
		split_menu.appendTo(split_button);

		// Add split-button
		split_button.appendTo(blockElem);

		for(row=0; row<6; row++){
			rhizo_row = $('<div>', {class: 'btn-group', style: 'padding: 0px; width: 100%;'})
			rhizo_row.attr('data-toggle', 'buttons');
			for(col=0; col<2; col++){
				// Create checkbox to track if a slot is active
				label = $('<label>', {class: 'btn btn-default active', html: 'Slot ' + (2*row+col+1), 
										title: 'Enable/Disable Slot',
										style: 'width: 50%', value: 2*row+col});
				checkbox = $('<input>', {type: 'checkbox', autocomplete: 'off'});
				checkbox.prop('checked');
				checkbox.appendTo(label);					
				label.appendTo(rhizo_row);
				// Add a 'start on slot' menu item
				split_menu_start_with = $('<li>', {html: '<a href="#" onclick="processRhizotronBin(this,' +
											(2*row+col) + ')">Start On Slot ' + (2*row+col+1) + '</a>', 
											title: 'Process enabled rhizotrons beginning with slot ' + (2*row+col+1) + '.'});
				split_menu_start_with.appendTo(split_menu); 
			}
			rhizo_row.appendTo(blockElem);
		}
		

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
	block.onValue = function(sequencePath, timestamp, value) {
		if (this.format && this.dataType === 1) {
			var decimalPlaces = parseInt(this.format);
			value = value.toFixed(decimalPlaces);
		}
		$('#' + this.id).html(value);
	}
}


// init a block object for displaying updates to a log sequence
function initLog(block) {
	block.nextLogEntryIndex = 0;
	block.prevTimestamps = [];
	block.prevValues = [];
	block.ready = false;

	block.addItem = function(timestamp, value) {
		var id = block.id + '_' + block.nextLogEntryIndex;
		block.nextLogEntryIndex++;
		createTimeValueItem(timestamp, value, id).prependTo($('#' + block.id));
		var maxCount = 50;
		if (block.nextLogEntryIndex > maxCount) {
			var removeIndex = block.nextLogEntryIndex - maxCount - 1;
			$('#' + block.id + '_' + removeIndex).remove();
		}
	}

	block.showPrevItems = function() {
		var len = block.prevValues.length;
		for (var i = 0; i < len; i++) {
			block.addItem(block.prevTimestamps[i] * 1000.0, block.prevValues[i]);
		}
		block.prevValues = [];
		block.prevTimestamps = [];
	}

	// fix(clean): remove?
	block.onready = function() {
		block.ready = true;
		block.showPrevItems();
		connectWebSocket();
	}

	// handle an update message for this sequence
	block.onValue = function(sequencePath, timestamp, value) {
		block.addItem(timestamp, value);
	}

	// request some historical data from server
	var handler = function(data) {
		var blockName = data.name;
		block.prevValues = data.values;
		block.prevTimestamps = data.timestamps;
		if (block.ready) {
			block.showPrevItems();
		}
	}
	$.get('/api/v1/resources' + block.sequencePaths[0], { count: 20 }, handler);
}


// init a block object for displaying updates to an image sequence
function initImageSequence(block) {

	// fix(clean): remove?
	block.onready = function() {
		connectWebSocket();
	}

	// handle an update message for this sequence
	block.onValue = function(sequencePath, timestamp, value) {
//		console.log('block: ' + this.id);
//		console.log('image: ' + value);
		var resourceName = this.sequencePaths[0];  // we assume the sequence name has a leading slash
		var d = new Date();
		$('#' + this.id + '_img').attr('src', '/api/v1/resources' + resourceName + '?' + d.getTime());  // add time to prevent caching
	}
}


function initPlot(block, blockSpec) {

	// create plot using manyplot library
	block.xData = createDataColumn('timestamp', []);
	block.xData.type = 'timestamp';
	block.yData = createDataColumn(blockSpec.label, []);
	block.yData.name = blockSpec.label;  // fix(soon): use sequence name
	var dataPairs = [
		{
			'xData': block.xData,
			'yData': block.yData,
		}
	];

	var addPlotHandler = function() {
		var canvas = document.getElementById(block.id + '_canvas');  // fix(soon): use block ID
		canvas.width = block.width;  // we set this earlier with jquery when creating the element, but that seems to have set the style width/height not canvas internal pixel dimensions
		canvas.height = block.height;
		block.plotHandler = createPlotHandler(canvas);
		block.plotHandler.plotter.setData(dataPairs);
	}

	// request some historical data from server
	var handler = function(data) {
		var blockName = data.name;
		var values = data.values;
		var timestamps = data.timestamps;
		var len = values.length;
		for (var i = 0; i < len; i++) {
			var val = values[i];
			if (val !== null) {
				values[i] = +val;  // convert to number
			}
		}
		block.xData.data = timestamps;  // we are updating the plotter's internal data; for now we assume we haven't received any live updates
		block.yData.data = values;
		if (!block.plotHandler) {
			addPlotHandler();
		}
		block.plotHandler.plotter.autoBounds(true);
		if ('min' in blockSpec && 'max' in blockSpec) {
			var frame = block.plotHandler.plotter.frames[0];
			frame.dataMinY = blockSpec.min;
			frame.dataMaxY = blockSpec.max;
		}
		block.plotHandler.drawPlot(null, null);
	}
	var url = '/api/v1/resources' + block.sequencePaths[0];
	var historySeconds = 24 * 60 * 60;
	var now = moment().valueOf();
	now = Math.round((now + 999) / 1000) * 1000;  // round up to next whole second
	var start = moment(now - (historySeconds * 1000)).toISOString();
	var end = moment(now).toISOString();
	var params = {
		count: 100000,
		start_timestamp: start,
		end_timestamp: end
	};
	$.get(url, params, handler);

	block.onready = function() {
		if (!block.plotHandler) {
			addPlotHandler();
		}
		block.plotHandler.drawPlot(null, null);
		$('#plot').show();
	}

	// handle an update message for this sequence
	block.onValue = function(sequencePath, timestamp, value) {
		var unixTimestamp = timestamp.unix();
		block.xData.data.push(unixTimestamp);
		block.yData.data.push(value);
		block.plotHandler.plotter.autoBounds(true);
		if ('min' in blockSpec && 'max' in blockSpec) {
			var frame = block.plotHandler.plotter.frames[0];
			frame.dataMinY = blockSpec.min;
			frame.dataMaxY = blockSpec.max;
		}
		block.plotHandler.drawPlot(null, null);
	}
}


// ======== rhizotron bin block classes ========
// Process the bin
function processRhizotronBin(e, slot) {
	// Get the block
	rhizo_bin_block = $(e.closest(".rhizo_binBlock"));

	// Get the bin number
	rhizo_bin = rhizo_bin_block.attr('value');

	// Get the block's checked checkboxes 
	checked_labels = rhizo_bin_block.find('label').filter('.active');

	// Determine the value we'll need to send as part of the message
	enable_mask = 0;
	
	// Loop through all the labels
	checked_labels.each(function(){
		enable_mask += 2**$(this).attr('value');
	});

	// Send a message to the client
	sendMessage("processBin", {binIndex: rhizo_bin, enableMask: enable_mask, startOn: slot});
}

// Select all rhizotrons in a rhizotron_bin
function enableAllRhizotrons(e) {
	$(e.closest(".rhizo_binBlock")).find('label').addClass('active');
}

// Select no rhizotrons in a rhizotron_bin
function disableAllRhizotrons(e) {
	$(e.closest(".rhizo_binBlock")).find('label').removeClass('active');
}
