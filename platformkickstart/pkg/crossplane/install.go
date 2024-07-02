package crossplane

import (
	"context"
	"fmt"
	"os"
	"time"

	crossplane "github.com/crossplane/crossplane/apis/pkg/v1"
	helmclient "github.com/mittwald/go-helm-client"
	"helm.sh/helm/v3/pkg/repo"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/tools/clientcmd"
	klog "k8s.io/klog/v2"
	"sigs.k8s.io/kind/pkg/cluster"

	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis/clientset/versioned"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/util"
)

const (
	crossplaneNamespace = "crossplane-system"
	apiextensionsPlural = "customresourcedefinitions"
)

func xrdReady(event watch.Event) (bool, error) {
	if event.Type == watch.Added {
		return true, nil
	}
	return false, nil
}

func waitForCrossplaneCRDs(client dynamic.Interface) error {
	watcher, err := client.Resource(schema.GroupVersionResource{
		Group:    "apiextensions.k8s.io",
		Version:  "v1",
		Resource: apiextensionsPlural,
	}).
		Watch(context.Background(), metav1.ListOptions{
			FieldSelector: fmt.Sprintf("metadata.name=%s", v1alpha1.CRDName),
		})
	if err != nil {
		return fmt.Errorf("couldn't create watcher: %w", err)
	}

	ticker := time.NewTicker(time.Second * 10)
	done := make(chan struct{})
	defer close(done)
	go util.LogEachTime("Wait for crossplane crds.", done, ticker)

	if err := util.WaitForCondition(watcher, xrdReady, time.Minute); err != nil {
		return fmt.Errorf("couldn't wait for XRDs: %w", err)
	}

	return nil
}

func providerReady(event watch.Event) (bool, error) {
	if event.Type == watch.Modified || event.Type == watch.Added {
		provider := crossplane.Provider{}

		uProvider, ok := event.Object.(*unstructured.Unstructured)
		if !ok {
			return false, fmt.Errorf("couldn't convert to unstructured")
		}

		if err := runtime.DefaultUnstructuredConverter.FromUnstructured(uProvider.Object, &provider); err != nil {
			return false, fmt.Errorf("couldn't convert to Provider: %w", err)
		}
		if provider.Status.GetCondition(crossplane.TypeHealthy).Status == corev1.ConditionTrue {
			return true, nil
		}
	}
	return false, nil
}

func WaitForProvider(client dynamic.Interface, name string) error {
	watcher, err := client.Resource(crossplane.SchemeGroupVersion.WithResource("providers")).
		Watch(context.Background(), metav1.ListOptions{
			FieldSelector: fmt.Sprintf("metadata.name=%s", name),
		})
	if err != nil {
		return fmt.Errorf("couldn't create watcher: %w", err)
	}
	defer watcher.Stop()

	ticker := time.NewTicker(time.Second * 10)
	done := make(chan struct{})
	defer close(done)

	go util.LogEachTime(fmt.Sprintf("Waiting for crossplane provider %q", name), done, ticker)

	if err := util.WaitForCondition(watcher, providerReady, time.Minute*5); err != nil {
		return fmt.Errorf("couldn't wait for crossplane provider: %w", err)
	}

	return nil
}

func Install(kubeconfigPath string) error {
	kubeConfigBytes, err := os.ReadFile(kubeconfigPath)
	if err != nil {
		return fmt.Errorf("couldn't read kubeconfig: %v", err)
	}

	opt := &helmclient.KubeConfClientOptions{
		Options: &helmclient.Options{
			Namespace:        crossplaneNamespace,
			RepositoryConfig: "/tmp/.helmcache",
			RepositoryCache:  "/tmp/.helmrepo",
			Debug:            true,
			Linting:          true,
			DebugLog: func(format string, v ...interface{}) {
				klog.V(5).Infof("[HELM]: "+format, v)
			},
		},
		KubeContext: "",
		KubeConfig:  kubeConfigBytes,
	}

	client, err := helmclient.NewClientFromKubeConf(opt, helmclient.Burst(1000), helmclient.Timeout(time.Second*10))
	if err != nil {
		return fmt.Errorf("couldn't create helm client from kubeconfig: %v", err)
	}

	chartRepo := repo.Entry{
		Name: "crossplane-stable",
		URL:  "https://charts.crossplane.io/stable",
	}

	if err := client.AddOrUpdateChartRepo(chartRepo); err != nil {
		return fmt.Errorf("couldn't add crossplane-stable helm repository: %v", err)
	}

	// helm install crossplane --namespace crossplane-system crossplane-stable/crossplane
	chartSpec := helmclient.ChartSpec{
		ReleaseName:     "crossplane",
		ChartName:       "crossplane-stable/crossplane",
		Namespace:       crossplaneNamespace,
		CreateNamespace: true,
		Wait:            true,
		UpgradeCRDs:     true,
		Timeout:         time.Minute * 5,
	}

	_, err = client.InstallOrUpgradeChart(context.Background(), &chartSpec, nil)
	if err != nil {
		return fmt.Errorf("couldn't install crossplane helm chart: %v", err)
	}

	k8sProvider := crossplane.Provider{
		TypeMeta: metav1.TypeMeta{
			Kind:       "Provider",
			APIVersion: "pkg.crossplane.io/v1",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name: "provider-kubernetes",
		},
		Spec: crossplane.ProviderSpec{
			PackageSpec: crossplane.PackageSpec{
				Package: "crossplane/provider-kubernetes:main",
			},
		},
	}

	config, err := clientcmd.BuildConfigFromFlags("", kubeconfigPath)
	if err != nil {
		return fmt.Errorf("unable to build config: %v", err)
	}

	dClient, err := dynamic.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to get dynamic client: %w", err)
	}
	unstructuredK8sProvider, err := runtime.DefaultUnstructuredConverter.ToUnstructured(k8sProvider.DeepCopyObject())
	if err != nil {
		return fmt.Errorf("couldn't obtain unstructured k8s provider: %w", err)
	}

	_, err = dClient.Resource(crossplane.SchemeGroupVersion.WithResource("providers")).
		Apply(context.Background(), k8sProvider.Name, &unstructured.Unstructured{Object: unstructuredK8sProvider}, metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to apply k8s provider: %w", err)
	}

	helmProvider := crossplane.Provider{
		TypeMeta: metav1.TypeMeta{
			Kind:       "Provider",
			APIVersion: "pkg.crossplane.io/v1",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name: "provider-helm",
		},
		Spec: crossplane.ProviderSpec{
			PackageSpec: crossplane.PackageSpec{
				Package: "crossplane/provider-helm:master",
			},
		},
	}
	unstructuredHelmProvider, err := runtime.DefaultUnstructuredConverter.ToUnstructured(helmProvider.DeepCopyObject())

	_, err = dClient.Resource(crossplane.SchemeGroupVersion.WithResource("providers")).
		Apply(context.Background(), helmProvider.Name, &unstructured.Unstructured{Object: unstructuredHelmProvider}, metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to apply ionos provider: %v", err)
	}

	uXRD, err := runtime.DefaultUnstructuredConverter.ToUnstructured(XRD.DeepCopyObject())
	if err != nil {
		return fmt.Errorf("unable to convert DigitalTwinPlatform XRD to unstructured: %w", err)
	}
	_, err = dClient.Resource(XRDGroupVersionResource).
		Apply(context.Background(), XRD.Name, &unstructured.Unstructured{Object: uXRD}, metav1.ApplyOptions{FieldManager: "crossplane"})

	if err := WaitForProvider(dClient, k8sProvider.Name); err != nil {
		return fmt.Errorf("couldn't wait for crossplane k8s provider: %w", err)
	}

	if err := WaitForProvider(dClient, helmProvider.Name); err != nil {
		return fmt.Errorf("couldn't wait for crossplane helm provider: %w", err)
	}

	if err := waitForCrossplaneCRDs(dClient); err != nil {
		return fmt.Errorf("couldn't wait for crossplane crds: %w", err)
	}

	return nil
}

func PrepareKindCluster(name, kubeconfig string) error {
	if err := cluster.NewProvider().Create(name, cluster.CreateWithKubeconfigPath(kubeconfig)); err != nil {
		return fmt.Errorf("couldn't create kind cluster: %w", err)
	}

	if err := Install(kubeconfig); err != nil {
		return fmt.Errorf("couldn't install crossplane: %w", err)
	}

	return nil
}

func DeployOnCluster(kubeconfig string, platform v1alpha1.DigitalTwinPlatform) error {
	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		return fmt.Errorf("unable to build config: %v", err)
	}

	client, err := versioned.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to get k8s client: %v", err)
	}

	if err := apis.CreateDigitalTwinPlatform(client, platform); err != nil {
		return fmt.Errorf("couldn't apply DigitalTwinPlatform object: %w", err)
	}

	return nil
}
