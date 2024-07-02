package crossplane

import (
	"testing"

	"gotest.tools/v3/assert"
)

func TestLoadFiles(t *testing.T) {
	err := LoadFiles()
	assert.NilError(t, err)

	assert.Equal(t, XRD.Name, "xdigitaltwinplatforms.crossplane.industry-fusion.com")
	assert.Equal(t, XRDGroupVersionResource.Resource, "compositeresourcedefinitions")
	assert.Equal(t, IONOSComposition.Name, "digitaltwinplatform-ionos")
	assert.Equal(t, IONOSCompositionGroupVersionResource.Resource, "compositions")
}
