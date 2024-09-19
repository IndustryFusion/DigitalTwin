// test/common.test.js

const chai = require('chai');
const sinon = require('sinon');
const expect = chai.expect;
const proxyquire = require('proxyquire');
const path = require('path');

chai.use(require('sinon-chai'));

describe('common', function () {
  let common;
  let fsStub;
  let configStub;
  let loggerStub;
  let dataDirectory;
  let deviceConfigPath;
  let catalogPath;

  beforeEach(function () {
    // Stub fs module
    fsStub = {
      writeFileSync: sinon.stub(),
      readFileSync: sinon.stub(),
      existsSync: sinon.stub(),
      mkdirSync: sinon.stub(),
    };

    // Stub config module
    dataDirectory = path.resolve('./data/');
    configStub = {
      data_directory: dataDirectory,
      getConfigName: sinon.stub().returns('config.json'),
    };

    // Stub logger
    loggerStub = {
      info: sinon.stub(),
      error: sinon.stub(),
      warn: sinon.stub(),
      debug: sinon.stub(),
    };

    // Proxyquire to inject stubs
    common = proxyquire('../lib/common', {
      fs: fsStub,
      '../config': configStub,
      './logger': {
        init: () => loggerStub,
      },
    });

    // Set up paths
    deviceConfigPath = path.resolve(dataDirectory, 'device.json');
    catalogPath = path.resolve(dataDirectory, 'catalog.json');

    // Initialize logger
    common.init(loggerStub);
  });

  afterEach(function () {
    sinon.restore();
  });

  describe('writeToJson', function () {
    it('should write data to JSON file', function () {
      const filename = 'test.json';
      const data = { key: 'value' };

      fsStub.writeFileSync.returns(null);

      const result = common.writeToJson(filename, data);

      expect(fsStub.writeFileSync).to.have.been.calledWith(
        filename,
        JSON.stringify(data, null, 4)
      );
      expect(loggerStub.info).to.have.been.calledWith('Object data saved to ' + filename);
      expect(result).to.be.false;
    });

    it('should log error if writing fails', function () {
      const filename = 'test.json';
      const data = { key: 'value' };
      const error = new Error('Write error');

      fsStub.writeFileSync.returns(error);

      const result = common.writeToJson(filename, data);

      expect(fsStub.writeFileSync).to.have.been.calledWith(
        filename,
        JSON.stringify(data, null, 4)
      );
      expect(loggerStub.error).to.have.been.calledWith('The file could not be written ', error);
      expect(result).to.be.true;
    });
  });

  describe('readFileToJson', function () {
    it('should read data from JSON file', function () {
      const filename = 'test.json';
      const data = { key: 'value' };
      fsStub.existsSync.returns(true);
      fsStub.readFileSync.returns(JSON.stringify(data));

      const result = common.readFileToJson(filename);

      expect(fsStub.readFileSync).to.have.been.calledWith(filename);
      expect(loggerStub.debug).to.have.been.calledWith(
        'Filename: ' + filename + ' Contents:',
        data
      );
      expect(result).to.deep.equal(data);
    });

    it('should log error if JSON is invalid', function () {
      const filename = 'test.json';
      fsStub.existsSync.returns(true);
      fsStub.readFileSync.returns('Invalid JSON');

      const result = common.readFileToJson(filename);

      expect(fsStub.readFileSync).to.have.been.calledWith(filename);
      expect(loggerStub.error).to.have.been.calledWith(
        'Improper JSON format:',
        sinon.match.string
      );
      expect(result).to.equal('Invalid JSON');
    });

    it('should return null if file does not exist', function () {
      const filename = 'test.json';
      fsStub.existsSync.returns(false);

      const result = common.readFileToJson(filename);

      expect(fsStub.readFileSync).to.not.have.been.called;
      expect(loggerStub.debug).to.have.been.calledWith(
        'Filename: ' + filename + ' Contents:',
        null
      );
      expect(result).to.be.null;
    });
  });

  describe('initializeDataDirectory', function () {
    it('should create data directory if it does not exist', function () {
      fsStub.existsSync.withArgs(dataDirectory).returns(false);

      common.initializeDataDirectory();

      expect(fsStub.mkdirSync).to.have.been.calledWith(dataDirectory);
    });

    it('should not create data directory if it exists', function () {
      fsStub.existsSync.withArgs(dataDirectory).returns(true);

      common.initializeDataDirectory();

      expect(fsStub.mkdirSync).to.not.have.been.called;
    });
  });

  describe('initializeFile', function () {
    it('should create file with data if it does not exist', function () {
      const filepath = 'test.json';
      const data = { key: 'value' };
      fsStub.existsSync.withArgs(filepath).returns(false);

      common.initializeFile(filepath, data);

      expect(fsStub.writeFileSync).to.have.been.calledWith(filepath, JSON.stringify(data, null, 4));
      expect(fsStub.existsSync).to.have.been.calledWith(filepath)
    });

    it('should not create file if it exists', function () {
      const filepath = 'test.json';
      const data = { key: 'value' };
      fsStub.existsSync.withArgs(filepath).returns(true);

      common.initializeFile(filepath, data);

      expect(fsStub.writeFileSync).to.not.have.been.called;
    });
  });

  describe('getDeviceConfigName', function () {
    it('should return device config path', function () {
      fsStub.existsSync.withArgs(deviceConfigPath).returns(true);

      const result = common.getDeviceConfigName();

      expect(result).to.equal(deviceConfigPath);
    });

    it('should initialize device config if it does not exist', function () {
      fsStub.existsSync.withArgs(deviceConfigPath).returns(false);

      sinon.stub(common, 'initializeDeviceConfig').callsFake(() => {
        fsStub.existsSync.withArgs(deviceConfigPath).returns(true);
      });

      const result = common.getDeviceConfigName();

      expect(common.initializeDeviceConfig).to.have.been.called;
      expect(result).to.equal(deviceConfigPath);
    });

    it('should exit process if device config cannot be found', function () {
      fsStub.existsSync.withArgs(deviceConfigPath).returns(false);

      sinon.stub(process, 'exit');

      common.getDeviceConfigName();

      expect(loggerStub.error).to.have.been.calledWith('Failed to find device config file!');
      expect(process.exit).to.have.been.calledWith(0);
    });
  });

  describe('getDeviceConfig', function () {
    it('should return device config data', function () {
      const configData = { key: 'value' };
      sinon.stub(common, 'getDeviceConfigName').returns(deviceConfigPath);
      sinon.stub(common, 'readFileToJson').withArgs(deviceConfigPath).returns(configData);

      const result = common.getDeviceConfig();

      expect(common.readFileToJson).to.have.been.calledWith(deviceConfigPath);
      expect(result).to.deep.equal(configData);
    });
  });

  describe('saveToDeviceConfig', function () {
    it('should save key-value pair to device config', function () {
      const key = 'some.key';
      const value = 'value';
      sinon.stub(common, 'getDeviceConfigName').returns(deviceConfigPath);
      sinon.stub(common, 'saveConfig');

      common.saveToDeviceConfig(key, value);

      expect(common.saveConfig).to.have.been.calledWith(deviceConfigPath, key, value);
    });
  });

  describe('saveConfig', function () {
    it('should save key-value pair to config file', function () {
      const fileName = 'config.json';
      const key = 'some.key';
      const value = 'value';
      const existingData = { existing: 'data' };
      const updatedData = { existing: 'data', some: { key: 'value' } };

      sinon.stub(common, 'readConfig').withArgs(fileName).returns(existingData);
      sinon.stub(common, 'writeConfig');

      common.saveConfig(fileName, key, value);

      expect(common.readConfig).to.have.been.calledWith(fileName);
      expect(common.writeConfig).to.have.been.calledWith(fileName, updatedData);
    });

    it('should handle nested keys', function () {
      const fileName = 'config.json';
      const key = 'level1.level2.key';
      const value = 'value';
      const existingData = { existing: 'data' };
      const updatedData = {
        existing: 'data',
        level1: {
          level2: {
            key: 'value',
          },
        },
      };

      sinon.stub(common, 'readConfig').withArgs(fileName).returns(existingData);
      sinon.stub(common, 'writeConfig');

      common.saveConfig(fileName, key, value);

      expect(common.writeConfig).to.have.been.calledWith(fileName, updatedData);
    });
  });

  describe('buildPath', function () {
    it('should replace placeholders with data', function () {
      const pathTemplate = '/api/{version}/resource/{id}';
      const data = ['v1', '123'];
      const expectedPath = '/api/v1/resource/123';

      const result = common.buildPath(pathTemplate, data);

      expect(result).to.equal(expectedPath);
    });

    it('should handle single placeholder', function () {
      const pathTemplate = '/api/resource/{id}';
      const data = '123';
      const expectedPath = '/api/resource/123';

      const result = common.buildPath(pathTemplate, data);

      expect(result).to.equal(expectedPath);
    });
  });

  describe('isBinary', function () {
    it('should return true for Buffer object', function () {
      const buffer = Buffer.from('test');

      const result = common.isBinary(buffer);

      expect(result).to.be.true;
    });

    it('should return true for object containing Buffer', function () {
      const obj = {
        data: Buffer.from('test'),
      };

      const result = common.isBinary(obj);

      expect(result).to.be.true;
    });

    it('should return false for non-binary object', function () {
      const obj = {
        data: 'string',
      };

      const result = common.isBinary(obj);

      expect(result).to.be.false;
    });
  });
});
