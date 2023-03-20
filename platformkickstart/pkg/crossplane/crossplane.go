package crossplane

import (
	_ "embed"
	"fmt"

	crossplaneresource "github.com/crossplane/crossplane/apis/apiextensions/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/yaml"
)

const (
	Compositions                 = "compositions"
	CompositeResourceDefinitions = "compositeresourcedefinitions"
)

var (
	//go:embed deploy/definition.yaml
	xrdYaml []byte
	// XRD is DigitalTwinPlatform Composite Resource Definition
	XRD crossplaneresource.CompositeResourceDefinition

	XRDGroupVersionResource schema.GroupVersionResource

	//go:embed deploy/local-composition.yaml
	localCompositionYaml []byte

	LocalComposition crossplaneresource.Composition

	LocalCompositionGroupVersionResource schema.GroupVersionResource

	//go:embed deploy/ionos-composition.yaml
	ionosCompositionYaml []byte

	// IONOSComposition is DigitalTwinPlatform IONOS Composition.
	IONOSComposition crossplaneresource.Composition

	IONOSCompositionGroupVersionResource schema.GroupVersionResource

	//go:embed deploy/private-composition.yaml
	privateCompositionYaml []byte

	// PrivateComposition is DigitalTwinPlatform Private Composition.
	PrivateComposition crossplaneresource.Composition

	PrivateCompositionGroupVersionResource schema.GroupVersionResource
)

func LoadFiles() error {
	if err := yaml.Unmarshal(xrdYaml, &XRD); err != nil {
		return fmt.Errorf("couldn't parse DigitalTwinPlatform Composite Resource Definition: %w", err)
	}
	XRDGroupVersionResource = XRD.GroupVersionKind().GroupVersion().WithResource(CompositeResourceDefinitions)

	if err := yaml.Unmarshal(localCompositionYaml, &LocalComposition); err != nil {
		return fmt.Errorf("coulnd't parse Local composition: %w", err)
	}
	LocalCompositionGroupVersionResource = LocalComposition.GroupVersionKind().GroupVersion().WithResource(Compositions)

	if err := yaml.Unmarshal(ionosCompositionYaml, &IONOSComposition); err != nil {
		return fmt.Errorf("couldn't parse DigitalTwinPlatform IONOS composition: %w", err)
	}
	IONOSCompositionGroupVersionResource = IONOSComposition.GroupVersionKind().GroupVersion().WithResource(Compositions)

	if err := yaml.Unmarshal(privateCompositionYaml, &PrivateComposition); err != nil {
		return fmt.Errorf("couldn't parse DigitalTwinPlatform Private composition: %w", err)
	}
	PrivateCompositionGroupVersionResource = PrivateComposition.GroupVersionKind().GroupVersion().WithResource(Compositions)

	return nil
}
