// test/ConnectionError.test.js

const chai = require('chai');
const expect = chai.expect;
const ConnectionError = require('../lib/ConnectionError');

describe('ConnectionError', function () {
  it('should create an instance of Error', function () {
    const error = new ConnectionError('An error occurred', 0);
    expect(error).to.be.instanceOf(Error);
  });

  it('should have the correct name', function () {
    const error = new ConnectionError('An error occurred', 1);
    expect(error.name).to.equal('ConnectorError');
  });

  it('should set the message property', function () {
    const message = 'Authorization failed';
    const error = new ConnectionError(message, 1);
    expect(error.message).to.equal(message);
  });

  it('should set the errno property', function () {
    const errno = 2;
    const error = new ConnectionError('Connection reset', errno);
    expect(error.errno).to.equal(errno);
  });

  it('should capture a stack trace', function () {
    const error = new ConnectionError('Test error', 0);
    expect(error.stack).to.be.a('string');
  });

  it('should handle missing errno parameter', function () {
    const error = new ConnectionError('An error occurred');
    expect(error.errno).to.be.undefined;
  });
});
