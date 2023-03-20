package apis

import (
	"fmt"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"
	"os"

	"sigs.k8s.io/yaml"
)

func FromPath(path string) (*v1alpha1.DigitalTwinPlatform, error) {
	claim := v1alpha1.DigitalTwinPlatform{}

	f, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("couldn't read platform file: %w", err)
	}

	if err := yaml.Unmarshal(f, &claim); err != nil {
		return nil, fmt.Errorf("couldn't unmarshal file: %w", err)
	}
	err = yaml.Unmarshal(f, &claim)

	return &claim, err
}
