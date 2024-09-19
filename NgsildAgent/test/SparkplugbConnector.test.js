// test/SparkplugbConnector.test.js

const chai = require('chai');
const sinon = require('sinon');
const expect = chai.expect;
const proxyquire = require('proxyquire');

chai.use(require('sinon-chai'));

describe('SparkplugbConnector', function () {
  let SparkplugbConnector;
  let sparkplugConnector;
  let ConnectionManagerStub;
  let connectionManagerMock;
  let commonStub;
  let loggerStub;
  let configStub;
  let clientPublishStub;

  beforeEach(function () {
    // Stub ConnectionManager
    clientPublishStub = sinon.stub().resolves(0);

    connectionManagerMock = {
      init: sinon.stub().resolves(),
      publish: clientPublishStub,
      connected: sinon.stub().returns(true),
      updateDeviceInfo: sinon.stub(),
    };

    ConnectionManagerStub = sinon.stub().returns(connectionManagerMock);

    // Stub common
    commonStub = {
      buildPath: sinon.stub(),
    };

    // Logger stub
    loggerStub = {
      info: sinon.stub(),
      error: sinon.stub(),
      warn: sinon.stub(),
      debug: sinon.stub(),
    };

    // Config stub
    configStub = {
      connector: {
        mqtt: {
          version: 'spBv1.0',
          host: 'localhost',
          port: 1883,
          secure: false,
          websockets: false,
        },
      },
    };

    // Proxyquire SparkplugbConnector to inject stubs
    SparkplugbConnector = proxyquire('../lib/SparkplugbConnector', {
      './ConnectionManager': ConnectionManagerStub,
      './common': commonStub,
    });

    // Instantiate SparkplugbConnector
    sparkplugConnector = new SparkplugbConnector(configStub, loggerStub);
  });

  afterEach(function () {
    sinon.restore();
  });

  describe('constructor', function () {
    it('should initialize with correct properties', function () {
      expect(sparkplugConnector.logger).to.equal(loggerStub);
      expect(sparkplugConnector.spbConf).to.equal(configStub.connector.mqtt);
      expect(sparkplugConnector.type).to.equal('mqtt');
      expect(sparkplugConnector.topics).to.be.an('object');
      expect(sparkplugConnector.pubArgs).to.deep.equal({
        qos: 1,
        retain: false,
      });
      expect(sparkplugConnector.client).to.equal(connectionManagerMock);
      expect(ConnectionManagerStub).to.have.been.calledWith(
        configStub.connector.mqtt,
        loggerStub
      );
    });
  });

  describe('init', function () {
    it('should initialize the client', async function () {
      await sparkplugConnector.init();
      expect(connectionManagerMock.init).to.have.been.calledOnce;
    });
  });

  describe('nodeBirth', function () {
    it('should publish node birth message', async function () {
      const devProf = {
        groupId: 'group1',
        edgeNodeId: 'edgeNode1',
      };

      commonStub.buildPath.returns('spBv1.0/group1/NBIRTH/edgeNode1/');

      const result = await sparkplugConnector.nodeBirth(devProf);

      expect(commonStub.buildPath).to.have.been.calledWith(
        sparkplugConnector.topics.metric_topic,
        [configStub.connector.mqtt.version, devProf.groupId, 'NBIRTH', devProf.edgeNodeId, '']
      );

      expect(connectionManagerMock.publish).to.have.been.calledWith(
        'spBv1.0/group1/NBIRTH/edgeNode1/',
        sinon.match({
          timestamp: sinon.match.number,
          metrics: sinon.match.array,
          seq: 0,
        }),
        sparkplugConnector.pubArgs
      );

      expect(result).to.equal(0);
    });
  });

  describe('deviceBirth', function () {
    it('should publish device birth message', async function () {
      const devProf = {
        groupId: 'group1',
        edgeNodeId: 'edgeNode1',
        deviceId: 'device1',
        componentMetric: [{ name: 'metric1', value: 100 }],
        subdeviceIds: ['subdevice1', 'subdevice2'],
      };

      commonStub.buildPath.callsFake((topicTemplate, data) => {
        return data.join('/');
      });

      await sparkplugConnector.deviceBirth(devProf);

      const expectedDeviceIds = ['subdevice1', 'subdevice2', 'device1'];
      expect(commonStub.buildPath.callCount).to.equal(expectedDeviceIds.length);

      expectedDeviceIds.forEach((deviceId, index) => {
        expect(commonStub.buildPath.getCall(index)).to.have.been.calledWith(
          sparkplugConnector.topics.metric_topic,
          [configStub.connector.mqtt.version, devProf.groupId, 'DBIRTH', devProf.edgeNodeId, deviceId]
        );

        expect(connectionManagerMock.publish.getCall(index)).to.have.been.calledWith(
          [configStub.connector.mqtt.version, devProf.groupId, 'DBIRTH', devProf.edgeNodeId, deviceId].join('/'),
          sinon.match({
            timestamp: sinon.match.number,
            metrics: devProf.componentMetric,
            seq: sinon.match.number,
          }),
          sparkplugConnector.pubArgs
        );
      });
    });
  });

  describe('publishData', function () {

    it('should log a warning for unknown deviceId', async function () {
      const devProf = {
        groupId: 'group1',
        edgeNodeId: 'edgeNode1',
        deviceId: 'device1',
        subdeviceIds: ['subdevice1'],
      };

      const payloadMetrics = [
        { deviceId: 'unknownDevice', name: 'metric1', value: 100 },
      ];

      const consoleWarnStub = sinon.stub(console, 'warn');

      await sparkplugConnector.publishData(devProf, payloadMetrics);

      expect(consoleWarnStub).to.have.been.calledWith('Unknown deviceid: unknownDevice');
      expect(connectionManagerMock.publish).to.not.have.been.called;

      consoleWarnStub.restore();
    });
  });

  describe('updateDeviceInfo', function () {
    it('should update device info in the client', function () {
      const deviceInfo = { deviceId: 'device1' };
      sparkplugConnector.updateDeviceInfo(deviceInfo);

      expect(connectionManagerMock.updateDeviceInfo).to.have.been.calledWith(deviceInfo);
    });
  });

  describe('connected', function () {
    it('should return true if client is connected', function () {
      connectionManagerMock.connected.returns(true);
      const result = sparkplugConnector.connected();
      expect(result).to.be.true;
    });

    it('should return false if client is not connected', function () {
      connectionManagerMock.connected.returns(false);
      const result = sparkplugConnector.connected();
      expect(result).to.be.false;
    });

    it('should return false if client does not exist', function () {
      sparkplugConnector.client = null;
      const result = sparkplugConnector.connected();
      expect(result).to.be.false;
    });
  });
});
