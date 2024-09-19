// test/CloudProxy.test.js

const chai = require('chai');
const sinon = require('sinon');
const expect = chai.expect;
const proxyquire = require('proxyquire');

chai.use(require('sinon-chai'));

describe('CloudProxy', function () {
  let CloudProxy;
  let cloudProxy;
  let loggerStub;
  let commonStub;
  let confStub;
  let SparkplugbConnectorStub;
  let ConnectionError;
  let jwtDecodeStub;
  let httpStub;
  let querystringStub;
  let deviceConfigStub;
  let spBProxyMock;
  let deviceId;

  beforeEach(function () {
    deviceId = 'device123';

    // Stub logger
    loggerStub = {
      info: sinon.stub(),
      error: sinon.stub(),
      warn: sinon.stub(),
      debug: sinon.stub(),
    };

    // Stub common module
    deviceConfigStub = {
      device_token: 'device_token',
      refresh_token: 'refresh_token',
      keycloak_url: 'http://keycloak.example.com',
      realm_id: 'realm_id',
      device_token_expire: null,
      activation_retries: 10,
      device_name: 'device_name',
      gateway_id: 'gateway_id',
      activation_code: 'activation_code',
      subdevice_ids: [],
    };

    commonStub = {
      getDeviceConfig: sinon.stub().returns(deviceConfigStub),
      saveToDeviceConfig: sinon.stub(),
    };

    // Stub conf module
    confStub = {
      connector: {
        mqtt: {
          sparkplugB: true,
        },
      },
    };

    // Stub SparkplugbConnector
    spBProxyMock = {
      updateDeviceInfo: sinon.stub(),
      init: sinon.stub().resolves(),
      nodeBirth: sinon.stub().resolves(),
      deviceBirth: sinon.stub().resolves(),
      connected: sinon.stub().returns(true),
      publishData: sinon.stub().resolves(),
    };

    SparkplugbConnectorStub = sinon.stub().returns(spBProxyMock);

    // Stub ConnectionError
    ConnectionError = sinon.stub();

    // Stub jwt-decode
    jwtDecodeStub = sinon.stub().returns({ exp: Math.floor(Date.now() / 1000) + 3600 });

    // Stub http
    httpStub = {
      request: sinon.stub(),
    };

    // Stub querystring
    querystringStub = {
      stringify: sinon.stub().callsFake((obj) => JSON.stringify(obj)),
    };

    // Use proxyquire to inject stubs
    CloudProxy = proxyquire('../lib/CloudProxy', {
      './common': commonStub,
      '../config': confStub,
      './SparkplugbConnector': SparkplugbConnectorStub,
      './ConnectionError': ConnectionError,
      'jwt-decode': jwtDecodeStub,
      http: httpStub,
      querystring: querystringStub,
    });

    // Instantiate CloudProxy
    cloudProxy = new CloudProxy(loggerStub, deviceId);
  });

  afterEach(function () {
    sinon.restore();
  });

  describe('constructor', function () {
    it('should initialize with correct properties', function () {
      expect(cloudProxy.logger).to.equal(loggerStub);
      expect(cloudProxy.birthMsgStatus).to.be.false;
      expect(cloudProxy.secret).to.deep.equal({
        deviceToken: deviceConfigStub.device_token,
        refreshToken: deviceConfigStub.refresh_token,
        refreshUrl: `${deviceConfigStub.keycloak_url}/${deviceConfigStub.realm_id}`,
        deviceTokenExpire: deviceConfigStub.device_token_expire,
      });
      expect(cloudProxy.max_retries).to.equal(deviceConfigStub.activation_retries);
      expect(cloudProxy.deviceId).to.equal(deviceId);
      expect(cloudProxy.deviceName).to.equal(deviceConfigStub.device_name);
      expect(cloudProxy.gatewayId).to.equal(deviceConfigStub.gateway_id);
      expect(cloudProxy.activationCode).to.equal(deviceConfigStub.activation_code);
      expect(cloudProxy.spBProxy).to.equal(spBProxyMock);
    });
  });

  describe('init', function () {
    it('should initialize spBProxy and send node and device birth messages', async function () {
      await cloudProxy.init();

      expect(spBProxyMock.init).to.have.been.calledOnce;

      if (cloudProxy.deviceId === cloudProxy.gatewayId) {
        expect(spBProxyMock.nodeBirth).to.have.been.calledOnce;
      } else {
        expect(loggerStub.info).to.have.been.calledWith('No Nodebirth sent because gatewayid != deviceid');
      }

      expect(spBProxyMock.deviceBirth).to.have.been.calledOnce;
      expect(cloudProxy.birthMsgStatus).to.be.true;
    });

    it('should handle ConnectionError during spBProxy.init', async function () {
      const error = new ConnectionError();
      error.errno = 1;
      spBProxyMock.init.rejects(error);

      const result = await cloudProxy.init();

      expect(loggerStub.error).to.have.been.calledWith('SparkplugB MQTT NBIRTH Metric not sent. Trying to refresh token.');
      expect(result).to.equal(1);
    });

    it('should handle unexpected errors during spBProxy.init', async function () {
      const error = new Error('Unexpected error');
      spBProxyMock.init.rejects(error);

      const result = await cloudProxy.init();

      expect(loggerStub.error).to.have.been.calledWith('Unexpected Error: ' + error.stack);
      expect(result).to.equal(2);
    });
  });

  describe('checkDeviceToken', function () {
    it('should not refresh token if deviceTokenExpire is in the future', async function () {
      cloudProxy.secret.deviceTokenExpire = Date.now() + 3600000; // 1 hour in future

      const result = await cloudProxy.checkDeviceToken();

      expect(result).to.equal(0);
    });

    it('should refresh token if deviceTokenExpire is in the past', async function () {
      cloudProxy.secret.deviceTokenExpire = Date.now() - 3600000; // 1 hour in past

      // Mock refreshToken function
      const refreshTokenData = JSON.stringify({
        access_token: 'new_access_token',
        refresh_token: 'new_refresh_token',
      });

      const reqMock = {
        on: sinon.stub(),
        write: sinon.stub(),
        end: sinon.stub(),
      };

      httpStub.request.callsArgWith(1, {
        statusCode: 200,
        on: (event, callback) => {
          if (event === 'data') {
            callback(refreshTokenData);
          }
          if (event === 'end') {
            callback();
          }
        },
      }).returns(reqMock);

      await cloudProxy.checkDeviceToken();

      expect(loggerStub.info).to.have.been.calledWith('Device token has expired - refreshing it now...');
      expect(commonStub.saveToDeviceConfig).to.have.been.calledWith('device_token', 'new_access_token');
      expect(commonStub.saveToDeviceConfig).to.have.been.calledWith('refresh_token', 'new_refresh_token');
      expect(spBProxyMock.updateDeviceInfo).to.have.been.called;
      expect(spBProxyMock.init).to.have.been.called;
    });
  });

  describe('dataSubmit', function () {
    beforeEach(function () {
      cloudProxy.birthMsgStatus = true;
    });

    it('should throw error if birthMsgStatus is false', async function () {
      cloudProxy.birthMsgStatus = false;

      try {
        await cloudProxy.dataSubmit({});
        expect.fail('Expected error to be thrown');
      } catch (err) {
        expect(err.message).to.equal('Session is not initialized.');
      }
    });

    it('should process and submit single metric', async function () {
      const metric = { n: 'metricName', v: 'metricValue', on: Date.now() };

      await cloudProxy.dataSubmit(metric);

      expect(spBProxyMock.publishData).to.have.been.calledOnce;

      const args = spBProxyMock.publishData.getCall(0).args;
      expect(args[1]).to.be.an('array').that.has.lengthOf(1);
      expect(args[1][0]).to.include({
        name: metric.n,
        value: metric.v,
        timestamp: metric.on,
      });
    });

    it('should process and submit array of metrics', async function () {
      const metrics = [
        { n: 'metric1', v: 'value1', on: Date.now() },
        { n: 'metric2', v: 'value2', on: Date.now() },
      ];

      await cloudProxy.dataSubmit(metrics);

      expect(spBProxyMock.publishData).to.have.been.calledOnce;

      const args = spBProxyMock.publishData.getCall(0).args;
      expect(args[1]).to.be.an('array').that.has.lengthOf(2);
      expect(args[1][0]).to.include({
        name: metrics[0].n,
        value: metrics[0].v,
      });
      expect(args[1][1]).to.include({
        name: metrics[1].n,
        value: metrics[1].v,
      });
    });
  });

  describe('checkOnlineState', function () {
    it('should return spBProxy connected state', async function () {
      spBProxyMock.connected.returns(true);

      const result = await cloudProxy.checkOnlineState();

      expect(result).to.be.true;
    });

    it('should return false if spBProxy is not connected', async function () {
      spBProxyMock.connected.returns(false);

      const result = await cloudProxy.checkOnlineState();

      expect(result).to.be.false;
    });
  });
});
