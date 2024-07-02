package apis

import (
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"
	"testing"

	"gotest.tools/v3/assert"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func TestDigitalTwinPlatformFromPath(t *testing.T) {
	t.Run("Correct", func(t *testing.T) {
		expected := v1alpha1.DigitalTwinPlatform{
			TypeMeta: metav1.TypeMeta{
				Kind:       "DigitalTwinPlatform",
				APIVersion: "crossplane.industry-fusion.com/v1alpha1",
			},
			ObjectMeta: metav1.ObjectMeta{
				Name:      "test",
				Namespace: "test",
			},
			Spec: v1alpha1.DigitalTwinPlatformSpec{
				Parameters: v1alpha1.Parameters{
					Size: "S",
				},
				CompositionSelector: v1alpha1.CompositionSelector{
					MatchLabels: v1alpha1.MatchLabels{
						Provider: "test",
					},
				},
				WriteConnectionSecretToRef: v1alpha1.WriteConnectionSecretToRef{
					Name: "test",
				},
			},
			Status: v1alpha1.DigitalTwinPlatformStatus{},
		}

		got, err := FromPath("testdata/digitaltwinplatform.yaml")
		assert.NilError(t, err)
		assert.DeepEqual(t, got, &expected)
	})

	t.Run("Cannot read", func(t *testing.T) {
		_, err := FromPath("no_exist")
		assert.ErrorContains(t, err, "couldn't read platform file")
	})

	t.Run("Wrong file", func(t *testing.T) {
		_, err := FromPath("testdata/wrong")
		assert.ErrorContains(t, err, "couldn't unmarshal file")
	})
}
