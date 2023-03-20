package ionos

import (
	"context"
	"encoding/base64"
	"errors"
	"flag"
	"fmt"
	"os"

	crossplanecommon "github.com/crossplane/crossplane-runtime/apis/common/v1"
	crossplanev1 "github.com/crossplane/crossplane/apis/pkg/v1"
	crossplanev1alpha1 "github.com/crossplane/crossplane/apis/pkg/v1alpha1"
	ionoscloud "github.com/ionos-cloud/crossplane-provider-ionoscloud/apis/v1alpha1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	applyconfigurationscorev1 "k8s.io/client-go/applyconfigurations/core/v1"
	applyconfigurationsmetav1 "k8s.io/client-go/applyconfigurations/meta/v1"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
	klog "k8s.io/klog/v2"
	"sigs.k8s.io/kind/pkg/cluster"

	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis/clientset/versioned"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crossplane"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/util"
)

const (
	kickstarterName = "digital-twin-platform-kickstart"
)

var (
	login    = flag.String("ionos-username", "", "IONOS account username.")
	password = flag.String("ionos-password", "", "IONOS account password.")
)

type ionos struct {
	platformObject v1alpha1.DigitalTwinPlatform
	debugMode      bool
	saveKubeconfig string
	username       string
	password       string
}

func New(parameters util.Parameters) (*ionos, error) {
	if *login == "" {
		return nil, errors.New("missing IONOS login, please set the \"ionos-username\" flag")
	}
	if *password == "" {
		return nil, errors.New("missing IONOS password, please set the \"ionos-password\" flag")
	}
	switch size := parameters.Claim.Spec.Parameters.Size; size {
	case "S", "M", "L":
		break
	default:
		return nil, fmt.Errorf("size parameter should be one of S,M,XL, cannot be: %s", size)
	}

	return &ionos{
		platformObject: parameters.Claim,
		debugMode:      parameters.Debug,
		saveKubeconfig: parameters.SaveKubeconfig,
		username:       *login,
		password:       *password}, nil
}

func (i *ionos) kickstarterCluster() (err error) {
	kickstarterDir, err := os.MkdirTemp("", "platform-kickstart-")
	if err != nil {
		return fmt.Errorf("couldn't prepare temporary directory: %w", err)
	}
	defer func() {
		if err := os.RemoveAll(kickstarterDir); err != nil {
			klog.Errorf("unable to delete temporary directory: %w", err)
		}
	}()

	kickstarterKubeconfig := kickstarterDir + "/kubeconfig"
	klog.Infof("Create %q kickstarter cluster.", kickstarterName)
	if err := crossplane.PrepareKindCluster(i.platformObject.Name, kickstarterKubeconfig); err != nil {
		return fmt.Errorf("couldn't prepare cluster: %w", err)
	}
	defer func() {
		if i.debugMode {
			return
		}
		if err := cluster.NewProvider().Delete(i.platformObject.Name, kickstarterKubeconfig); err != nil {
			klog.Errorf("unable to clean cluster: %w", err)
		}
	}()

	if err := applyConfiguration(kickstarterKubeconfig, i.username, i.password); err != nil {
		return fmt.Errorf("couldn't install ionos scenarion in %q cluster: %w", kickstarterName, err)
	}

	klog.Info("Deploying platform")
	if err := crossplane.DeployOnCluster(kickstarterKubeconfig, i.platformObject); err != nil {
		return fmt.Errorf("couldn't deploy platform: %w", err)
	}

	// Obtain kubeconfig from secret.
	config, err := clientcmd.BuildConfigFromFlags("", kickstarterKubeconfig)
	if err != nil {
		return fmt.Errorf("unable to build config: %v", err)
	}
	kindClusterClient, err := kubernetes.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to create dynamic client: %w", err)
	}
	kubeconfig, err := util.KubeconfigFromConnectionSecret(kindClusterClient, i.platformObject.Spec.WriteConnectionSecretToRef.Name, i.platformObject.Namespace)
	if err != nil {
		return fmt.Errorf("couldn't watch for DigitalTwinPlatform secret: %w", err)
	}

	err = os.WriteFile(i.saveKubeconfig, kubeconfig, os.FileMode(0777))
	if err != nil {
		return fmt.Errorf("couldn't save k8s secret to file: %w", err)
	}

	// All parts done, there is no things to debug. Kind should be deleted.
	return nil
}

func (i *ionos) Run() error {
	klog.Info("Prepare temporary cluster and install crossplane package in to.")
	if err := i.kickstarterCluster(); err != nil {
		return err
	}

	klog.Info("Install crossplane package in to the IONOS cluster.")
	ionosClusterConfig, err := clientcmd.BuildConfigFromFlags("", i.saveKubeconfig)
	if err != nil {
		return fmt.Errorf("unable to build config: %v", err)
	}
	ionosClusterDynamicClient, err := versioned.NewForConfig(ionosClusterConfig)
	if err != nil {
		return fmt.Errorf("unable to create dynamic client: %w", err)
	}

	if err := crossplane.Install(i.saveKubeconfig); err != nil {
		return fmt.Errorf("couldn't install crossplane in IONOS cluster: %v", err)
	}

	if err := applyConfiguration(i.saveKubeconfig, i.username, i.password); err != nil {
		return fmt.Errorf("couldn't install ionos scenario in %q cluster: %w", kickstarterName, err)
	}

	if err := apis.CreateDigitalTwinPlatform(ionosClusterDynamicClient, i.platformObject); err != nil {
		return fmt.Errorf("couldn't apply DigitalTwinPlatform object in IONOS cluster: %w", err)
	}

	return nil
}

func applyConfiguration(kubeconfig, username, password string) error {
	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		return fmt.Errorf("unable to build config: %w", err)
	}

	dClient, err := dynamic.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to obtain k8s dynamic client: %w", err)
	}

	ionosControllerConfig := crossplanev1alpha1.ControllerConfig{
		TypeMeta: metav1.TypeMeta{
			Kind:       "ControllerConfig",
			APIVersion: "pkg.crossplane.io/v1alpha1",
		},
		ObjectMeta: metav1.ObjectMeta{Name: "provider-ionos-config"},
		Spec: crossplanev1alpha1.ControllerConfigSpec{
			Args: []string{"--unique-names"},
		},
	}

	uIonosControllerConfig, err := runtime.DefaultUnstructuredConverter.ToUnstructured(ionosControllerConfig.DeepCopyObject())
	if err != nil {
		return fmt.Errorf("unable to convert ionos controller config to unstructed: %w", err)
	}
	_, err = dClient.Resource(crossplanev1alpha1.SchemeGroupVersion.WithResource("controllerconfigs")).
		Apply(context.Background(), ionosControllerConfig.Name, &unstructured.Unstructured{Object: uIonosControllerConfig}, metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to create ionos provider controller config: %w", err)
	}

	ionosProvider := crossplanev1.Provider{
		TypeMeta: metav1.TypeMeta{
			Kind:       "Provider",
			APIVersion: "pkg.crossplane.io/v1",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name: "provider-ionos",
		},
		Spec: crossplanev1.ProviderSpec{
			PackageSpec: crossplanev1.PackageSpec{
				Package: "ghcr.io/ionos-cloud/crossplane-provider-ionoscloud:latest",
			},
			ControllerConfigReference: &crossplanev1.ControllerConfigReference{
				Name: ionosControllerConfig.Name,
			},
		},
		Status: crossplanev1.ProviderStatus{},
	}

	uIonosProvider, err := runtime.DefaultUnstructuredConverter.ToUnstructured(ionosProvider.DeepCopyObject())
	if err != nil {
		return fmt.Errorf("unable to convert IONOS provider to unstructured: %w", err)
	}
	_, err = dClient.Resource(crossplanev1.SchemeGroupVersion.WithResource("providers")).
		Apply(context.Background(), ionosProvider.Name, &unstructured.Unstructured{Object: uIonosProvider}, metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to create ionos provider: %w", err)
	}

	uIONOSComposition, err := runtime.DefaultUnstructuredConverter.ToUnstructured(crossplane.IONOSComposition.DeepCopyObject())
	if err != nil {
		return fmt.Errorf("unable to convert IONOS composition object to unstructured: %w", err)
	}
	_, err = dClient.Resource(crossplane.IONOSCompositionGroupVersionResource).
		Apply(context.Background(), crossplane.IONOSComposition.Name, &unstructured.Unstructured{Object: uIONOSComposition}, metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to create ionos composition: %w", err)
	}

	if err := crossplane.WaitForProvider(dClient, ionosProvider.Name); err != nil {
		return fmt.Errorf("couldn't wait for crossplane ionos provider: %w", err)
	}

	base64pw := make([]byte, base64.StdEncoding.EncodedLen(len(password)))
	base64.StdEncoding.Encode(base64pw, []byte(password))

	ionosProviderSecretName := "ionos-provider-secret"
	ionosProviderSecretAPIVersion := "v1"
	ionosProviderSecretKind := "Secret"
	ionosProviderSecret := applyconfigurationscorev1.SecretApplyConfiguration{
		TypeMetaApplyConfiguration: applyconfigurationsmetav1.TypeMetaApplyConfiguration{
			Kind:       &ionosProviderSecretKind,
			APIVersion: &ionosProviderSecretAPIVersion,
		},
		ObjectMetaApplyConfiguration: &applyconfigurationsmetav1.ObjectMetaApplyConfiguration{
			Name: &ionosProviderSecretName,
		},
		Data: map[string][]byte{"credentials": []byte(fmt.Sprintf("{\"user\":%q,\"password\":%q}", username, base64pw))},
	}

	kubernetesClient, err := kubernetes.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to get k8s client: %w", err)
	}

	res, err := kubernetesClient.CoreV1().Secrets("crossplane-system").
		Apply(context.Background(), &ionosProviderSecret, metav1.ApplyOptions{FieldManager: "application/apply-patch"})
	if err != nil {
		klog.Errorf("secret apply response: %v", res)
		return fmt.Errorf("unable to apply secret: %v", err)
	}

	ionosProviderConfig := ionoscloud.ProviderConfig{
		TypeMeta: metav1.TypeMeta{
			Kind:       "ProviderConfig",
			APIVersion: "ionoscloud.crossplane.io/v1alpha1",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name: "digitaltwin", //TODO(Creatone): Consider change to more obvious.
		},
		Spec: ionoscloud.ProviderConfigSpec{
			Credentials: ionoscloud.ProviderCredentials{
				Source: "Secret",
				CommonCredentialSelectors: crossplanecommon.CommonCredentialSelectors{
					SecretRef: &crossplanecommon.SecretKeySelector{
						SecretReference: crossplanecommon.SecretReference{
							Name:      "ionos-provider-secret",
							Namespace: "crossplane-system",
						},
						Key: "credentials",
					},
				},
			},
		},
	}

	uIonosProviderConfig, err := runtime.DefaultUnstructuredConverter.ToUnstructured(ionosProviderConfig.DeepCopyObject())
	if err != nil {
		return fmt.Errorf("unable to convert ionos provider config to unstructed: %w", err)
	}
	_, err = dClient.Resource(ionoscloud.SchemeGroupVersion.WithResource("providerconfigs")).
		Apply(context.Background(), ionosProviderConfig.Name, &unstructured.Unstructured{Object: uIonosProviderConfig}, metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to create ionos provider config: %w", err)
	}

	return nil
}
