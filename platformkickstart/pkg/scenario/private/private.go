package private

import (
	"context"
	"fmt"
	"os"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	applyconfigurationscorev1 "k8s.io/client-go/applyconfigurations/core/v1"
	applyconfigurationsmetav1 "k8s.io/client-go/applyconfigurations/meta/v1"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"

	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis/clientset/versioned"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crossplane"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/util"
)

type private struct {
	Claim      v1alpha1.DigitalTwinPlatform
	Kubeconfig string
}

func (p private) Run() error {
	if err := crossplane.Install(p.Kubeconfig); err != nil {
		return fmt.Errorf("couldn't install crossplane on the desired cluster")
	}

	if err := p.applyConfiguration(); err != nil {
		return fmt.Errorf("couldn't install private scenario: %w", err)
	}

	config, err := clientcmd.BuildConfigFromFlags("", p.Kubeconfig)
	if err != nil {
		return fmt.Errorf("unable to build config: %w", err)
	}

	client, err := versioned.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to create k8s client: %w", err)
	}

	if err := apis.CreateDigitalTwinPlatform(client, p.Claim); err != nil {
		return fmt.Errorf("couldn't apply DigitalTwinPlatform object in private cluster: %w", err)
	}

	return nil
}

func (p private) applyConfiguration() error {
	config, err := clientcmd.BuildConfigFromFlags("", p.Kubeconfig)
	if err != nil {
		return fmt.Errorf("unable to build config: %w", err)
	}

	dClient, err := dynamic.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to obtain k8s dynamic client: %w", err)
	}

	uPrivateComposition, err := runtime.DefaultUnstructuredConverter.ToUnstructured(crossplane.PrivateComposition.DeepCopyObject())
	if err != nil {
		return fmt.Errorf("unable to convert private composition object to unstructured: %w", err)
	}
	_, err = dClient.Resource(crossplane.PrivateCompositionGroupVersionResource).
		Apply(context.Background(), crossplane.PrivateComposition.Name,
			&unstructured.Unstructured{Object: uPrivateComposition},
			metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to create private composition: %w", err)
	}

	kubeconfigBytes, err := os.ReadFile(p.Kubeconfig)
	if err != nil {
		return fmt.Errorf("unable to read kubeconfig file: %w", err)
	}

	providerSecretAPIVersion := "v1"
	providerSecretKind := "Secret"
	providerSecretName := p.Claim.Name + "-kubeconfig"
	providersSecret := applyconfigurationscorev1.SecretApplyConfiguration{
		TypeMetaApplyConfiguration: applyconfigurationsmetav1.TypeMetaApplyConfiguration{
			Kind:       &providerSecretKind,
			APIVersion: &providerSecretAPIVersion,
		},
		ObjectMetaApplyConfiguration: &applyconfigurationsmetav1.ObjectMetaApplyConfiguration{
			Name: &providerSecretName,
		},
		Data: map[string][]byte{"kubeconfig": kubeconfigBytes},
	}

	client, err := kubernetes.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to obtain k8s client: %w", err)
	}
	res, err := client.CoreV1().Secrets("crossplane-system").
		Apply(context.Background(), &providersSecret, metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to apply secret, got response: %+q and error: %w", res, err)
	}

	return nil
}

func New(parameters util.Parameters) (*private, error) {
	return &private{Claim: parameters.Claim, Kubeconfig: parameters.Kubeconfig}, nil
}
