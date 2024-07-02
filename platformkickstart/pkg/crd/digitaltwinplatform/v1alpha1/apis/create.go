package apis

import (
	"context"
	"fmt"
	"time"

	crossplanecommon "github.com/crossplane/crossplane-runtime/apis/common/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/watch"

	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"
	applyconfiguration "github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis/applyconfiguration/digitaltwinplatform/v1alpha1"
	platformclient "github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis/clientset/versioned"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/util"
)

const (
	timeout = time.Minute * 20
	tick    = time.Second * 30
)

func CreateDigitalTwinPlatform(client platformclient.Interface, platform v1alpha1.DigitalTwinPlatform) error {
	applyConfiguration := applyconfiguration.DigitalTwinPlatform(platform.Name, platform.Namespace)
	applyConfigurationSpec := applyconfiguration.DigitalTwinPlatformSpec()
	applyConfigurationSpec.Parameters = applyconfiguration.Parameters().WithSize(platform.Spec.Parameters.Size)
	applyConfigurationSpec.WriteConnectionSecretToRef = applyconfiguration.WriteConnectionSecretToRef().WithName(platform.Spec.WriteConnectionSecretToRef.Name)
	applyConfigurationSpec.CompositionSelector = applyconfiguration.CompositionSelector()
	applyConfigurationSpec.CompositionSelector.MatchLabels = applyconfiguration.MatchLabels().WithProvider(platform.Spec.CompositionSelector.MatchLabels.Provider)

	applyConfiguration = applyConfiguration.WithSpec(applyConfigurationSpec)

	_, err := client.CrossplaneV1alpha1().DigitalTwinPlatforms(platform.Namespace).Apply(
		context.Background(),
		applyConfiguration,
		metav1.ApplyOptions{
			FieldManager: util.FieldManager,
		},
	)
	if err != nil {
		return fmt.Errorf("couldn't create object: %w", err)
	}
	watcher, err := client.CrossplaneV1alpha1().DigitalTwinPlatforms(platform.Namespace).Watch(context.Background(),
		metav1.ListOptions{FieldSelector: fmt.Sprintf("metadata.name=%s", platform.Name)})
	if err != nil {
		return fmt.Errorf("couldn't create watcher: %w", err)
	}
	defer watcher.Stop()

	ticker := time.NewTicker(tick)
	done := make(chan struct{})
	defer close(done)

	go util.LogEachTime(fmt.Sprintf("Waiting for %q %s to be ready.", platform.Name, platform.Kind), done, ticker)

	if err := util.WaitForCondition(watcher, digitalTwinPlatformReady, timeout); err != nil {
		return fmt.Errorf("couldn't wait for DigitalTwin platform: %w", err)
	}

	return nil
}

func digitalTwinPlatformReady(event watch.Event) (bool, error) {
	if event.Type == watch.Added || event.Type == watch.Modified {
		platform, ok := event.Object.(*v1alpha1.DigitalTwinPlatform)
		if !ok {
			return false, fmt.Errorf("couldn't convert to DigitalTwinPlatform")
		}
		if platform.Status.GetCondition(crossplanecommon.TypeReady).Status == corev1.ConditionTrue {
			return true, nil
		}
	}
	return false, nil
}
