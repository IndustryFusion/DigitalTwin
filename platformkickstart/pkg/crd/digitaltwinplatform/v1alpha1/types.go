package v1alpha1

import (
	xpv1 "github.com/crossplane/crossplane-runtime/apis/common/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// +genclient
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

// DigitalTwinPlatform is the CRD.
type DigitalTwinPlatform struct {
	metav1.TypeMeta `json:",inline"`
	// +optional
	// Standard object's metadata.
	metav1.ObjectMeta `json:"metadata"`
	// Specification of the desired behavior of DigitalTwinPlatform.
	Spec DigitalTwinPlatformSpec `json:"spec"`

	// +optional
	// Observed status of DigitalTwinPlatform.
	Status DigitalTwinPlatformStatus `json:"status"`
}

// DigitalTwinPlatformSpec is a desired state description of DigitalTwinPlatform.
type DigitalTwinPlatformSpec struct {
	Parameters                 Parameters                 `json:"parameters"`
	CompositionSelector        CompositionSelector        `json:"compositionSelector"`
	WriteConnectionSecretToRef WriteConnectionSecretToRef `json:"writeConnectionSecretToRef"`
}

type Parameters struct {
	Size string `json:"size"`
}

type CompositionSelector struct {
	MatchLabels MatchLabels `json:"matchLabels"`
}

type MatchLabels struct {
	Provider string `json:"provider"`
}

type WriteConnectionSecretToRef struct {
	Name string `json:"name"`
}

// DigitalTwinPlatformStatus describes the lifecycle status of DigitalTwinPlatform.
type DigitalTwinPlatformStatus struct {
	xpv1.ConditionedStatus `json:",inline"`
}

// DigitalTwinPlatformList is the list of DigitalTwinPlatforms.
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
type DigitalTwinPlatformList struct {
	metav1.TypeMeta `json:",inline"`
	// Standard list metadata.
	metav1.ListMeta `json:"metadata"`
	// List of DigitalTwinPlatforms.
	Items []DigitalTwinPlatform `json:"items"`
}
