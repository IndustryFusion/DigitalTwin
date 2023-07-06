var deviceId = keycloakSession.getContext().getRequestHeaders()
    .getRequestHeader("X-DeviceID");

if (deviceId.length === 0) {
    exports = "INVALID_DEVICE_ID";
} else {
    exports = deviceId[0];
}