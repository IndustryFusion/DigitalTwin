package local

import (
	"context"
	"fmt"
	"strings"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	rbacv1 "k8s.io/client-go/applyconfigurations/rbac/v1"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
	klog "k8s.io/klog/v2"

	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crossplane"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/util"
)

type local struct {
	platformObject v1alpha1.DigitalTwinPlatform
	kubeconfig     string
}

func New(parameters util.Parameters) (*local, error) {

	if parameters.Debug {
		return nil, fmt.Errorf("debug mode is not supported")
	}

	return &local{
		platformObject: parameters.Claim,
		kubeconfig:     parameters.SaveKubeconfig,
	}, nil
}

func (l *local) Run() error {
	klog.Info("Preparing kind cluster.")

	if err := crossplane.PrepareKindCluster(l.platformObject.Name, l.kubeconfig); err != nil {
		return fmt.Errorf("couldn't prepare kind cluster: %w", err)
	}

	klog.Info("Applying local scenario yaml's.")
	if err := applyConfiguration(l.kubeconfig); err != nil {
		return fmt.Errorf("couldn't apply local scenario yamls: %w", err)
	}

	klog.Info("Deploying platform.")
	if err := crossplane.DeployOnCluster(l.kubeconfig, l.platformObject); err != nil {
		return fmt.Errorf("couldn't deploy platform: %w", err)
	}

	return nil
}

func applyConfiguration(kubeconfig string) error {
	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		return fmt.Errorf("unable to build config: %v", err)
	}

	client, err := kubernetes.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to get k8s client: %w", err)
	}

	list, err := client.CoreV1().ServiceAccounts("crossplane-system").
		List(context.Background(), metav1.ListOptions{})
	if err != nil {
		return fmt.Errorf("unable to obtain service accounts: %w", err)
	}

	k8sProvider := "provider-kubernetes"
	helmProvider := "provider-helm"

	search := func(list []corev1.ServiceAccount, provider *string) {
		for _, item := range list {
			if strings.Contains(item.Name, *provider) {
				name := item.Name
				*provider = name
				break
			}
		}
	}

	search(list.Items, &helmProvider)
	search(list.Items, &k8sProvider)

	clusterAdmin := rbacv1.RoleRef().WithKind("ClusterRole").WithName("cluster-admin")

	k8sProviderSubjects := rbacv1.Subject().WithName(k8sProvider).WithKind("ServiceAccount").WithNamespace("crossplane-system")
	k8sProviderClusterRoleBiding := rbacv1.ClusterRoleBinding("provider-kubernetes-admin-binding").
		WithRoleRef(clusterAdmin).
		WithSubjects(k8sProviderSubjects).
		WithNamespace("crossplane-system")

	_, err = client.RbacV1().ClusterRoleBindings().Apply(
		context.Background(),
		k8sProviderClusterRoleBiding,
		metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("couldn't create k8s provider cluster role binding: %w", err)
	}

	helmProviderSubjects := rbacv1.Subject().WithName(helmProvider).WithKind("ServiceAccount").WithNamespace("crossplane-system")
	helmProviderClusterRoleBinding := rbacv1.ClusterRoleBinding("provider-helm-admin-binding").
		WithRoleRef(clusterAdmin).
		WithSubjects(helmProviderSubjects).
		WithNamespace("crossplane-system")
	_, err = client.RbacV1().ClusterRoleBindings().Apply(
		context.Background(),
		helmProviderClusterRoleBinding,
		metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("couldn't create helm provider cluster role binding: %w", err)
	}

	dClient, err := dynamic.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("unable to get dynamic client: %w", err)
	}

	uLocalComposition, err := runtime.DefaultUnstructuredConverter.ToUnstructured(crossplane.LocalComposition.DeepCopyObject())
	if err != nil {
		return fmt.Errorf("unable to convert local composition object to unstructured: %w", err)
	}
	_, err = dClient.Resource(crossplane.LocalCompositionGroupVersionResource).
		Apply(context.Background(), crossplane.LocalComposition.Name, &unstructured.Unstructured{Object: uLocalComposition}, metav1.ApplyOptions{FieldManager: util.FieldManager})
	if err != nil {
		return fmt.Errorf("unable to apply local composition: %v", err)
	}

	return nil
}
