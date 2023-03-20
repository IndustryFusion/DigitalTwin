package scenario

import (
	"errors"

	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/scenario/ionos"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/scenario/local"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/scenario/private"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/util"
)

type Scenario interface {
	Run() error
}

func New(parameters util.Parameters) (Scenario, error) {
	switch parameters.Claim.Spec.CompositionSelector.MatchLabels.Provider {
	case "ionos":
		return ionos.New(parameters)
	case "local":
		return local.New(parameters)
	case "private":
		return private.New(parameters)
	default:
		return nil, errors.New("not supported")
	}
}
