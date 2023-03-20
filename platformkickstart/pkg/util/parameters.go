package util

import "github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"

type Parameters struct {
	Claim          v1alpha1.DigitalTwinPlatform
	Debug          bool
	SaveKubeconfig string
	Kubeconfig     string
}
