// test/ConnectionManager.test.js

const chai = require('chai');
const sinon = require('sinon');
const expect = chai.expect;
const proxyquire = require('proxyquire');

chai.use(require('sinon-chai'));

describe('ConnectionManager', function () {
  let ConnectionManager;
  let mqttStub;
  let mqttConnectAsyncStub;
  let mqttClientMock;
  let ConnectionErrorStub;
  let loggerStub;

  beforeEach(function () {
    // Stub the mqtt module
    mqttClientMock = {
      on: sinon.stub(),
      publishAsync: sinon.stub().resolves(),
      endAsync: sinon.stub().resolves(),
      connected: true,
    };

    mqttConnectAsyncStub = sinon.stub().resolves(mqttClientMock);

    mqttStub = {
      connectAsync: mqttConnectAsyncStub,
    };

    // Stub the ConnectionError class
    ConnectionErrorStub = sinon.stub();

    // Logger stub
    loggerStub = {
      info: sinon.stub(),
      error: sinon.stub(),
      warn: sinon.stub(),
      debug: sinon.stub(),
    };

    // Proxyquire the ConnectionManager module
    ConnectionManager = proxyquire('../lib/ConnectionManager', {
      mqtt: mqttStub,
      './ConnectionError': ConnectionErrorStub,
    });
  });

  afterEach(function () {
    sinon.restore();
  });

  describe('constructor', function () {
    it('should initialize with correct properties', function () {
      const conf = {
        host: 'localhost',
        port: 1883,
        websockets: false,
        secure: false,
        keepalive: 60,
        retries: 30,
        qos: 1,
        retain: false,
      };

      const connectionManager = new ConnectionManager(conf, loggerStub);

      expect(connectionManager.host).to.equal('localhost');
      expect(connectionManager.port).to.equal(1883);
      expect(connectionManager.websockets).to.be.false;
      expect(connectionManager.secure).to.be.false;
      expect(connectionManager.keepalive).to.equal(60);
      expect(connectionManager.max_retries).to.equal(30);
      expect(connectionManager.pubArgs).to.deep.equal({
        qos: 1,
        retain: false,
      });
      expect(connectionManager.isLive).to.be.false;
      expect(connectionManager.deviceInfo).to.deep.equal({});
      expect(connectionManager.logger).to.equal(loggerStub);
    });
  });

  describe('init', function () {
    let conf;
    let connectionManager;

    beforeEach(function () {
      conf = {
        host: 'localhost',
        port: 1883,
        websockets: false,
        secure: false,
        keepalive: 60,
        retries: 30,
        qos: 1,
        retain: false,
      };

      connectionManager = new ConnectionManager(conf, loggerStub);
    });

    it('should initialize MQTT client with correct URL and options (MQTT protocol)', async function () {
      await connectionManager.init();

      const expectedUrl = 'mqtt://localhost:1883';

      expect(mqttConnectAsyncStub).to.have.been.calledWith(expectedUrl, {
        username: undefined,
        password: undefined,
        rejectUnauthorized: false,
      });

      expect(mqttClientMock.on).to.have.been.calledWith('connect', sinon.match.func);
      expect(mqttClientMock.on).to.have.been.calledWith('reconnect', sinon.match.func);
      expect(mqttClientMock.on).to.have.been.calledWith('offline', sinon.match.func);
      expect(mqttClientMock.on).to.have.been.calledWith('error', sinon.match.func);
      expect(mqttClientMock.on).to.have.been.calledWith('end', sinon.match.func);

      expect(connectionManager.authorized).to.be.true;
    });

    it('should handle secure MQTT connections', async function () {
      connectionManager.secure = true;

      await connectionManager.init();

      const expectedUrl = 'mqtts://localhost:1883';

      expect(mqttConnectAsyncStub).to.have.been.calledWith(expectedUrl, sinon.match.object);
    });

    it('should handle websocket connections', async function () {
      connectionManager.websockets = true;

      await connectionManager.init();

      const expectedUrl = 'ws://localhost:1883';

      expect(mqttConnectAsyncStub).to.have.been.calledWith(expectedUrl, sinon.match.object);
    });

    it('should handle secure websocket connections', async function () {
      connectionManager.secure = true;
      connectionManager.websockets = true;

      await connectionManager.init();

      const expectedUrl = 'wss://localhost:1883';

      expect(mqttConnectAsyncStub).to.have.been.calledWith(expectedUrl, sinon.match.object);
    });

    it('should handle errors during connection', async function () {
      const error = new Error('Connection failed');
      mqttConnectAsyncStub.rejects(error);

      const connectionErrorInstance = new Error('Connection failed');
      ConnectionErrorStub.withArgs(error.message, 0).returns(connectionErrorInstance);

      try {
        await connectionManager.init();
        expect.fail('Expected error to be thrown');
      } catch (err) {
        expect(loggerStub.info).to.have.been.calledWith('MQTT connection error: Connection failed');
        expect(err.message).to.equal(connectionErrorInstance.message);
      }
    });

    it('should end existing client before reconnecting', async function () {
      connectionManager.client = mqttClientMock;

      await connectionManager.init();

      expect(mqttClientMock.endAsync).to.have.been.calledOnce;
    });
  });

  describe('publish', function () {
    it('should publish message to specified topic', async function () {
      const conf = {
        host: 'localhost',
        port: 1883,
        websockets: false,
        secure: false,
        qos: 1,
        retain: false,
      };
      const connectionManager = new ConnectionManager(conf, loggerStub);
      connectionManager.client = mqttClientMock;

      const topic = 'test/topic';
      const message = { key: 'value' };
      const options = { qos: 1, retain: false };

      await connectionManager.publish(topic, message, options);

      expect(mqttClientMock.publishAsync).to.have.been.calledWith(
        topic,
        JSON.stringify(message),
        options
      );
    });

    it('should return 0 on successful publish', async function () {
      const conf = {
        host: 'localhost',
        port: 1883,
        websockets: false,
        secure: false,
        qos: 1,
        retain: false,
      };
      const connectionManager = new ConnectionManager(conf, loggerStub);
      connectionManager.client = mqttClientMock;

      const result = await connectionManager.publish('test/topic', { key: 'value' }, {});

      expect(result).to.equal(0);
    });
  });

  describe('connected', function () {
    it('should return client.connected when client exists', function () {
      const conf = {
        host: 'localhost',
        port: 1883,
      };
      const connectionManager = new ConnectionManager(conf, loggerStub);
      connectionManager.client = mqttClientMock;

      mqttClientMock.connected = true;
      expect(connectionManager.connected()).to.be.true;

      mqttClientMock.connected = false;
      expect(connectionManager.connected()).to.be.false;
    });

    it('should return false when client does not exist', function () {
      const conf = {
        host: 'localhost',
        port: 1883,
      };
      const connectionManager = new ConnectionManager(conf, loggerStub);

      expect(connectionManager.connected()).to.be.false;
    });
  });

  describe('authorized', function () {
    it('should return true when authorized', function () {
      const conf = {
        host: 'localhost',
        port: 1883,
      };
      const connectionManager = new ConnectionManager(conf, loggerStub);
      connectionManager.authorized = true;

      expect(connectionManager.authorized).to.be.true;
    });

    it('should return false when not authorized', function () {
      const conf = {
        host: 'localhost',
        port: 1883,
      };
      const connectionManager = new ConnectionManager(conf, loggerStub);
      connectionManager.authorized = false;

      expect(connectionManager.authorized).to.be.false;
    });
  });

  describe('createConnectionError', function () {
    it('should return ConnectionError with errno 0 for errno -111', function () {
      const conf = {};
      const connectionManager = new ConnectionManager(conf, loggerStub);

      const error = new Error('Connection refused');
      error.errno = -111;

      const connectionErrorInstance = new Error('Connection error');
      ConnectionErrorStub.withArgs('Connection refused', 0).returns(connectionErrorInstance);

      const result = connectionManager.createConnectionError(error);

      expect(ConnectionErrorStub).to.have.been.calledWith('Connection refused', 0);
      expect(result).to.equal(connectionErrorInstance);
    });

    it('should return ConnectionError with errno 1 for code 5', function () {
      const conf = {};
      const connectionManager = new ConnectionManager(conf, loggerStub);

      const error = new Error('Not authorized');
      error.code = 5;

      const connectionErrorInstance = new Error('Connection error');
      ConnectionErrorStub.withArgs('Not authorized', 1).returns(connectionErrorInstance);

      const result = connectionManager.createConnectionError(error);

      expect(ConnectionErrorStub).to.have.been.calledWith('Not authorized', 1);
      expect(result).to.equal(connectionErrorInstance);
    });

    it('should return original error if no matching errno or code', function () {
      const conf = {};
      const connectionManager = new ConnectionManager(conf, loggerStub);

      const error = new Error('Unknown error');

      const result = connectionManager.createConnectionError(error);

      expect(ConnectionErrorStub).to.not.have.been.called;
      expect(result).to.equal(error);
    });
  });

  describe('updateDeviceInfo', function () {
    it('should update deviceInfo property', function () {
      const conf = {};
      const connectionManager = new ConnectionManager(conf, loggerStub);

      const deviceInfo = {
        device_id: 'device1',
        device_token: 'token1',
      };

      connectionManager.updateDeviceInfo(deviceInfo);

      expect(connectionManager.deviceInfo).to.equal(deviceInfo);
    });
  });
});
