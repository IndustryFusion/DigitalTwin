package main

import (
	_ "embed"
	"errors"
	"flag"
	"os"

	klog "k8s.io/klog/v2"

	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis"
	platformcrossplane "github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crossplane"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/scenario"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/util"
)

var (
	platformK8sObject  = flag.String("file", "", "DigitalTwinPlatform k8s object.")
	debugMode          = flag.Bool("debug", false, "Debug mode.")
	kubeconfigSavePath = flag.String("save-kubeconfig", "./kubeconfig", "Kubeconfig save path.")
	kubeconfig         = flag.Lookup("kubeconfig")
)

func parseRequiredFlags() error {
	flag.Parse()

	if *platformK8sObject == "" {
		return errors.New("missing --file flag")
	}

	return nil
}

func main() {
	if err := parseRequiredFlags(); err != nil {
		klog.Errorf("Couldn't run platform kickstart: %v", err)
		os.Exit(1)
	}

	if err := platformcrossplane.LoadFiles(); err != nil {
		klog.Errorf("Couldn't load platform files: %v", err)
	}

	source, err := apis.FromPath(*platformK8sObject)
	if err != nil {
		klog.Errorf("Couldn't parse DigitalTwinPlatform k8s object: %v", err)
		os.Exit(1)
	}

	s, err := scenario.New(util.Parameters{
		Claim:          *source,
		Debug:          *debugMode,
		SaveKubeconfig: *kubeconfigSavePath,
		Kubeconfig:     kubeconfig.Value.String(),
	})
	if err != nil {
		klog.Errorf("Couldn't obtain scenario from source: %v", err.Error())
		os.Exit(1)
	}

	klog.Infof("Trying to run %q scenario.", source.Spec.CompositionSelector.MatchLabels.Provider)
	err = s.Run()
	if err != nil {
		klog.Errorf("Couldn't run scenario: %v", err)
		os.Exit(1)
	}

	klog.Infof("Scenario %q completed.", source.Spec.CompositionSelector.MatchLabels.Provider)
}
