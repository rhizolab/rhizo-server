// cached values
var g_emailAddressExists = null;
var g_emailAddressExistsText = null;
var g_userNameExists = null;
var g_userNameExistsText = null;


// use REST API to check whether a user already exists with the given email address
// (cached version)
function emailAddressExists(emailAddress) {
	if (g_emailAddressExistsText !== emailAddress) {
		checkEmailAddressExists(emailAddress, false);
	}
	return g_emailAddressExists;
}


// use REST API to check whether a user already exists with the given user name
// (cached version)
function userNameExists(userName) {
	if (g_userNameExistsText !== userName) {
		checkUserNameExists(userName, false);
	}
	return g_userNameExists;
}


// use REST API to check whether a user already exists with the given email address
// (if the email address is valid)
function checkEmailAddressExists(emailAddress, async) {
	if (validEmailAddress(emailAddress)) {
		var handler = function(data) {
			g_emailAddressExists = data.exists;
			g_emailAddressExistsText = emailAddress
		}
		$.ajax({
			url: '/api/v1/users/' + emailAddress + '?check_exists=1',
			success: handler,
			async: async,
		});
	}
}


// use REST API to check whether a user already exists with the given user name
// (if the user name is valid)
function checkUserNameExists(userName, async) {
	if (validUserName(userName)) {
		var handler = function(data) {
			g_userNameExists = data.exists;
			g_userNameExistsText = userName;
		}
		$.ajax({
			url: '/api/v1/users/' + userName + '?check_exists=1',
			success: handler,
			async: async,
		});
	}
}


// a simplistic email validation (will allow many invalid emails,
// but at least makes sure the user attempted to enter something email-address-like)
function validEmailAddress(emailAddress) {
    var re = /\S+@\S+\.\S+/;
    return re.test(emailAddress);
}


// returns true if user name is valid
// fix(later): better validation
function validUserName(userName) {
	return userName.length >= 4;
}


// returns true if password is valid
// fix(later): better validation
function validPassword(password) {
	return password.length >= 8;
}


// returns true if organization name is valid
// fix(later): better validation
function validOrganizationName(orgName) {
	return orgName.length >= 0;
}


// returns true if folder name is valid
// fix(later): better validation
function validFolderName(folderName) {
	return folderName.length >= 0;
}
