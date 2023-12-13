var deviceIdH = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-DeviceID");
var  deviceIdS = userSession.getNote('deviceId');
if (deviceIdS !== null && deviceIdS !== undefined) {
    exports = deviceIdS;
} else {
    userSession.setNote('deviceId', deviceIdH[0]);
    exports = deviceIdH[0];
}