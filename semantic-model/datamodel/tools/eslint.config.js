const neostandard = require('neostandard');
const globals = require('globals');

module.exports = [
  ...neostandard({
    globals: [globals.browser]
  }),
  {
    files: ['tests/**/*.js'],
    languageOptions: {
      globals: globals.mocha
    }
  },
  {
    rules: {
      '@stylistic/semi': [1, 'always']
    }
  }
];
