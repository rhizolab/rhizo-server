// create a text editor instance;
// currently this is a light-weight wrapper around an ACE editor;
// it keeps track of whether the text has been modified/saved
function createEditor(id, mode, modCallback) {

	// create editor object
	var editor = {};
	editor.modified = false;
	editor.editorObj = null;
	editor.modCallback = modCallback;

	// get the current text contained within the editor
	editor.value = function() {
		return this.editorObj.getValue();
	}

	// clear the modified flag that indicates whether user has modified the text since it was last saved
	editor.clearModified = function() {
		this.modified = false;
		if (this.modCallback)
			this.modCallback();
	}

	// initialize the editor
	editor.start = function() {
		this.editorObj = ace.edit(id);
		this.editorObj.setTheme('ace/theme/github');
		this.editorObj.getSession().setMode('ace/mode/' + mode);
		this.editorObj.getSession().on('change', function(e) {
			editor.modified = true;
			if (editor.modCallback) {
				editor.modCallback();
			}
		});
	}

	// warn before leave page; code adapted from Manylabs doc editor code
	window.addEventListener('beforeunload', function (e) {
		console.log('beforeunload');
		if (editor.modified) {
			// setTimeout(save, 0); // fix(later): we could do something like this to save changes, but what if user doesn't want to save changes?
			var confirmationMessage = 'You have unsaved changes that will be lost if you leave this page.';
			(e || window.event).returnValue = confirmationMessage; // Gecko, IE
			return confirmationMessage; // Webkit, Safari, Chrome, etc.
		}
	});

	return editor;
}


// save script on ctrl-s; code adapted from Manylabs doc editor code
// assumes the current page implements a save() function
$(document).keydown(function(event) {
	if (!(String.fromCharCode(event.which).toLowerCase() == 's' && event.ctrlKey) && !(event.which == 19)) return true; // 19 for Mac
	save(false);
	event.preventDefault();
	return false;
});
