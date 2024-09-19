// test/DataSubmission.test.js

const chai = require('chai');
const sinon = require('sinon');
const expect = chai.expect;
const proxyquire = require('proxyquire');

chai.use(require('sinon-chai'));

describe('DataSubmission', function () {
  let DataSubmission;
  let schemaValidationStub;
  let dataSchemaStub;
  let configStub;
  let DbManagerStub;
  let dbManagerMock;
  let validateIriStub;
  let connectorStub;
  let loggerStub;
  let validatorFunction;
  let submissionCallback;
  let dataSubmissionInstance; // To access sessionIsOnline in tests

  beforeEach(function () {
    // Stub for schema-validation
    validatorFunction = sinon.stub();
    schemaValidationStub = {
      validateSchema: sinon.stub().returns(validatorFunction),
    };

    // Stub for dataSchema
    dataSchemaStub = {};

    // Stub for config
    configStub = {
      connector: {
        mqtt: {
          sparkplugB: true,
        },
      },
    };

    // Stub for DbManager
    dbManagerMock = {
      init: sinon.stub().resolves(),
      preInsert: sinon.stub().resolves(),
      acknowledge: sinon.stub().resolves(),
      mostRecentPropertyUpdateStrategy: sinon.stub().resolves({ msgs: [], finished: true }),
      isEnabled: sinon.stub().returns(true),
    };
    DbManagerStub = sinon.stub().returns(dbManagerMock);

    // Stub for validate-iri as an object with validateIri method
    validateIriStub = {
      validateIri: sinon.stub(),
    };

    // Stub for connector
    connectorStub = {
      checkOnlineState: sinon.stub().resolves(true),
      dataSubmit: sinon.stub().resolves(),
    };

    // Stub for logger
    loggerStub = {
      info: sinon.stub(),
      warn: sinon.stub(),
      error: sinon.stub(),
      debug: sinon.stub(),
    };

    // Proxyquire DataSubmission with stubs
    DataSubmission = proxyquire('../lib/DataSubmission', {
      './schema-validator': schemaValidationStub,
      './schemas/data': dataSchemaStub,
      '../config': configStub,
      './DbManager': DbManagerStub,
      'validate-iri': validateIriStub, // Now an object with validateIri
    });

    // Instantiate DataSubmission
    dataSubmissionInstance = new DataSubmission(connectorStub, loggerStub);
    dataSubmissionInstance.dbManager = dbManagerMock; // Assign dbManager before getting callback
    submissionCallback = dataSubmissionInstance.getSubmissionCallback();
  });

  afterEach(function () {
    sinon.restore();
  });

  describe('constructor', function () {
    it('should initialize with correct properties', function () {
      expect(dataSubmissionInstance.logger).to.equal(loggerStub);
      expect(dataSubmissionInstance.connector).to.equal(connectorStub);
      expect(schemaValidationStub.validateSchema).to.have.been.calledWith(dataSchemaStub);
      expect(dataSubmissionInstance.validator).to.equal(validatorFunction);
      expect(dataSubmissionInstance.sessionIsOnline).to.equal(1);
      expect(dataSubmissionInstance.dbManager).to.equal(dbManagerMock);
    });
  });

  describe('init', function () {
    it('should initialize dbManager and call its init method', async function () {
      await dataSubmissionInstance.init();

      expect(DbManagerStub).to.have.been.calledWith(configStub);
      expect(dbManagerMock.init).to.have.been.calledOnce;
    });
  });

  describe('getSubmissionCallback', function () {
    it('should process valid messages correctly', async function () {
      // Arrange
      const msgs = [
        {
          n: 'metric1',
          v: 100,
          t: 'Property',
          on: 1627891234567,
        },
        {
          n: 'metric2',
          v: 200,
          t: 'PropertyJson',
          on: 1627891234568,
        },
      ];

      // Mock validateIri to return false (valid IRI)
      validateIriStub.validateIri.withArgs('metric1').returns(false);
      validateIriStub.validateIri.withArgs('metric2').returns(false);

      // Mock validator to return null (valid)
      validatorFunction.withArgs(msgs[0]).returns(null);
      validatorFunction.withArgs(msgs[1]).returns(null);

      // Act
      await submissionCallback(msgs);

      // Assert
      // preInsert should be called for each valid message with status 1
      expect(dbManagerMock.preInsert).to.have.been.calledTwice;
      expect(dbManagerMock.preInsert.firstCall).to.have.been.calledWith(msgs[0], 1);
      expect(dbManagerMock.preInsert.secondCall).to.have.been.calledWith(msgs[1], 1);

      // connector.dataSubmit should be called with modified messages
      expect(connectorStub.dataSubmit).to.have.been.calledOnce;
      const expectedMessages = [
        { n: 'Property/metric1', on: 1627891234567, v: 100 },
        { n: 'PropertyJson/metric2', on: 1627891234568, v: 200 },
      ];
      const actualMessages = connectorStub.dataSubmit.firstCall.args[0];
      expect(actualMessages).to.deep.equal(expectedMessages);

      // acknowledge should be called with msgKeys
      expect(dbManagerMock.acknowledge).to.have.been.calledOnce;
      const expectedMsgKeys = [
        { n: 'metric1', on: 1627891234567 },
        { n: 'metric2', on: 1627891234568 },
      ];
      expect(dbManagerMock.acknowledge).to.have.been.calledWith(expectedMsgKeys);
    });

    it('should ignore messages with invalid IRI', async function () {
      // Arrange
      const msgs = [
        {
          n: 'invalid-iri',
          v: 100,
          t: 'Property',
          on: 1627891234567,
        },
      ];

      // Mock validateIri to return true (invalid IRI)
      validateIriStub.validateIri.withArgs('invalid-iri').returns(true);

      // Act
      await submissionCallback(msgs);

      // Assert
      expect(loggerStub.warn).to.have.been.calledWith('Metric name invalid-iri not an IRI. Ignoring message.');
      expect(dbManagerMock.preInsert).to.not.have.been.called;
    });

    it('should ignore messages with invalid JSON in PropertyJson type', async function () {
      // Arrange
      const msgs = [
        {
          n: 'metric1',
          v: 'invalid-json',
          t: 'PropertyJson',
          on: 1627891234567,
        },
      ];

      // Mock validateIri to return false (valid IRI)
      validateIriStub.validateIri.withArgs('metric1').returns(false);

      // Since JSON.parse is inside try-catch, we'll simulate it throwing
      const originalJSONParse = JSON.parse;
      sinon.stub(JSON, 'parse').throws(new Error('Invalid JSON'));

      // Act
      await submissionCallback(msgs);

      // Restore JSON.parse
      JSON.parse.restore();

      // Assert
      expect(loggerStub.warn).to.have.been.calledWith('Metric name metric1 with invalid-json not a parsable JSON object. Ignoring message.');
      expect(dbManagerMock.preInsert).to.not.have.been.called;
    });

    it('should set default type to "Property" if t is undefined or null', async function () {
      // Arrange
      const msgs = [
        {
          n: 'metric1',
          v: 100,
          on: 1627891234567,
        },
      ];

      // Mock validateIri to return false (valid IRI)
      validateIriStub.validateIri.withArgs('metric1').returns(false);

      // Mock validator to return null (valid)
      const processedMsg = {
        n: 'metric1',
        v: 100,
        t: 'Property',
        on: 1627891234567,
      };
      validatorFunction.withArgs(processedMsg).returns(null);

      // Act
      await submissionCallback(msgs);

      // Assert
      expect(dbManagerMock.preInsert).to.have.been.calledOnce;
      expect(dbManagerMock.preInsert).to.have.been.calledWith({
        n: 'Property/metric1',
        v: 100,
        on: 1627891234567,
      }, 1);

      expect(connectorStub.dataSubmit).to.have.been.calledOnce;
      const expectedMessages = [
        { n: 'Property/metric1', on: 1627891234567, v: 100 },
      ];
      expect(connectorStub.dataSubmit.firstCall.args[0]).to.deep.equal(expectedMessages);

      expect(dbManagerMock.acknowledge).to.have.been.calledOnce;
      const expectedMsgKeys = [
        { n: 'metric1', on: 1627891234567 },
      ];
      expect(dbManagerMock.acknowledge).to.have.been.calledWith(expectedMsgKeys);
    });

    it('should handle messages with datasetId', async function () {
      // Arrange
      const msgs = [
        {
          n: 'metric1',
          v: 100,
          d: 'dataset1',
          on: 1627891234567,
        },
      ];

      // Mock validateIri for n and datasetId
      validateIriStub.validateIri.withArgs('metric1').returns(false);
      validateIriStub.validateIri.withArgs('dataset1').returns(false);

      // Mock validator to return null (valid)
      const processedMsg = {
        n: 'Property/metric1',
        v: 100,
        on: 1627891234567,
        properties: { values: ['dataset1'], keys: ['datasetId'] }
      };
      validatorFunction.withArgs(processedMsg).returns(null);

      // Act
      await submissionCallback(msgs);

      // Assert
      // preInsert should be called with status 1
      expect(dbManagerMock.preInsert).to.have.been.calledOnce;

      // connector.dataSubmit should be called with modified message
      expect(connectorStub.dataSubmit).to.have.been.calledOnce;

      // acknowledge should be called with msgKeys
      expect(dbManagerMock.acknowledge).to.have.been.calledOnce;

      expect(dbManagerMock.acknowledge).to.have.been.calledWith([]);
    });

    it('should handle validation failures', async function () {
      // Arrange
      const msgs = [
        {
          n: 'metric1',
          v: 100,
          t: 'Property',
          on: 1627891234567,
        },
      ];

      // Mock validateIri to return false (valid IRI)
      validateIriStub.validateIri.withArgs('metric1').returns(false);

      // Mock validator to return validation errors
      const validationErrors = [{ message: 'Invalid value' }];
      validatorFunction.withArgs(msgs[0]).returns(validationErrors);

      // Act
      await submissionCallback(msgs);

      // Assert
      expect(loggerStub.warn).to.have.been.calledWith(`Data submission - Validation failed. ${JSON.stringify(validationErrors)}`);
      expect(dbManagerMock.preInsert).to.have.been.calledOnce;
      expect(dbManagerMock.preInsert).to.have.been.calledWith(msgs[0], 0);
    });

    it('should handle messages not being an array', async function () {
      // Arrange
      const msg = {
        n: 'metric1',
        v: 100,
        t: 'Property',
        on: 1627891234567,
      };

      // Mock validateIri to return false (valid IRI)
      validateIriStub.validateIri.withArgs('metric1').returns(false);

      // Mock validator to return null (valid)
      validatorFunction.withArgs(msg).returns(null);

      // Act
      await submissionCallback(msg);

      // Assert
      expect(dbManagerMock.preInsert).to.have.been.calledOnce;
      expect(dbManagerMock.preInsert).to.have.been.calledWith(msg, 1);

      expect(connectorStub.dataSubmit).to.have.been.calledOnce;
      const expectedMessages = [
        { n: 'Property/metric1', on: 1627891234567, v: 100 },
      ];
      expect(connectorStub.dataSubmit.firstCall.args[0]).to.deep.equal(expectedMessages);

      expect(dbManagerMock.acknowledge).to.have.been.calledOnce;
      const expectedMsgKeys = [
        { n: 'metric1', on: 1627891234567 },
      ];
      expect(dbManagerMock.acknowledge).to.have.been.calledWith(expectedMsgKeys);
    });

    it('should handle session being offline and enter catch-up mode', async function () {
      // Arrange
      const msgs = [
        {
          n: 'metric1',
          v: 100,
          t: 'Property',
          on: 1627891234567,
        },
      ];

      // Mock validateIri to return false (valid IRI)
      validateIriStub.validateIri.withArgs('metric1').returns(false);

      // Mock validator to return null (valid)
      validatorFunction.withArgs(msgs[0]).returns(null);

      // Mock checkOnlineState to first return false, then true
      connectorStub.checkOnlineState.onFirstCall().resolves(false); // offline
      connectorStub.checkOnlineState.onSecondCall().resolves(true); // back online

      // Simulate session being offline and then online
      dataSubmissionInstance.sessionIsOnline = 0;
      dbManagerMock.isEnabled.returns(true);

      // Mock mostRecentPropertyUpdateStrategy to return some messages
      const dbMsgs = [
        {
          n: 'metric2',
          t: 'Property',
          v: 200,
          on: 1627891234568,
        },
      ];
      dbManagerMock.mostRecentPropertyUpdateStrategy.resolves({ msgs: dbMsgs, finished: true });

      // Modify connectorStub.dataSubmit to resolve
      connectorStub.dataSubmit.resolves();

      // Act
      await submissionCallback(msgs); // First call, sessionIsOnline = 0

      // After the first call, sessionIsOnline should be set based on checkOnlineState
      // Since checkOnlineState returned false, sessionIsOnline remains 0

      // Now, simulate being back online by calling submissionCallback again
      await submissionCallback(msgs);

      // Assert
      // After second call, sessionIsOnline should be set to 1
      expect(dataSubmissionInstance.sessionIsOnline).to.equal(1);

      // dataSubmit should have been called with the fetched messages
      expect(connectorStub.dataSubmit).to.have.been.calledWith([
        { n: 'Property/metric2', on: 1627891234568, v: 200 },
      ]);

      // acknowledge should have been called with msgKeys from db
      expect(dbManagerMock.acknowledge).to.have.been.calledWith([
        { n: 'metric2', on: 1627891234568 },
      ]);
    });

    it('should handle dataSubmit failure and set sessionIsOnline to 0', async function () {
      // Arrange
      const msgs = [
        {
          n: 'metric1',
          v: 100,
          t: 'Property',
          on: 1627891234567,
        },
      ];

      // Mock validateIri to return false (valid IRI)
      validateIriStub.validateIri.withArgs('metric1').returns(false);

      // Mock validator to return null (valid)
      validatorFunction.withArgs(msgs[0]).returns(null);

      // Mock checkOnlineState to return true (online)
      connectorStub.checkOnlineState.resolves(true);

      // Mock dataSubmit to reject
      connectorStub.dataSubmit.rejects(new Error('Submission failed'));

      // Act
      await submissionCallback(msgs);

      // Assert
      expect(connectorStub.dataSubmit).to.have.been.calledOnce;
      expect(dataSubmissionInstance.sessionIsOnline).to.equal(0);
      expect(loggerStub.warn).to.have.been.calledWith('Could not submit sample: Error: Submission failed');
      // acknowledge should not be called due to failure
      expect(dbManagerMock.acknowledge).to.not.have.been.called;
    });
  });

  describe('init method', function () {
    it('should initialize dbManager', async function () {
      await dataSubmissionInstance.init();

      expect(DbManagerStub).to.have.been.calledWith(configStub);
      expect(dbManagerMock.init).to.have.been.calledOnce;
    });
  });
});
