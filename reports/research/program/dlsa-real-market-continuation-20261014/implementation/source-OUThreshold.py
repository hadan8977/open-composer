import torch
import torch.nn as nn
import numpy as np


class OUThreshold(nn.Module):
    def __init__(
            self,
            lookback=30,
            random_seed=0,
            device="cpu",
            signal_threshold=1.25,
            r2_threshold=0.25,
            use_robust_estimators=False,
        ):
        
        super(OUThreshold, self).__init__()
        self.is_trainable = False
        self.is_frictions_model = False

        self.random_seed = random_seed 
        torch.manual_seed(self.random_seed)
        self.device = torch.device(device)
        
        self.signal_threshold = signal_threshold
        self.r2_threshold = r2_threshold
        self.use_robust_estimators = use_robust_estimators
        
        # Dummy parameter to make the model compatible with PyTorch's parameter management
        self.dummy_param = nn.Parameter(torch.zeros(1, dtype=torch.float, device=self.device))

    def robust_mean(self, x):
        """Compute robust mean using median."""
        return torch.median(x, dim=1)[0]

    def robust_variance(self, x):
        """Compute robust variance using Median Absolute Deviation (MAD)."""
        median = torch.median(x, dim=1)[0].unsqueeze(1)
        mad = torch.median(torch.abs(x - median), dim=1)[0]
        # Scale factor 1.4826 makes MAD consistent with standard deviation for normal distributions
        return (1.4826 * mad) ** 2

    def robust_covariance(self, x, y):
        """Compute robust covariance using pairwise method."""
        n = x.shape[1]
        x_med = torch.median(x, dim=1)[0].unsqueeze(1)
        y_med = torch.median(y, dim=1)[0].unsqueeze(1)
        
        # Use sign of deviations from median
        x_sign = torch.sign(x - x_med)
        y_sign = torch.sign(y - y_med)
        
        # Compute robust covariance using pairwise method
        cov = torch.sum(x_sign * y_sign, dim=1) / (4 * n)
        
        # Scale to match standard covariance scale
        x_mad = torch.median(torch.abs(x - x_med), dim=1)[0]
        y_mad = torch.median(torch.abs(y - y_med), dim=1)[0]
        ret = cov * (1.4826**2) * x_mad * y_mad

        # Extra multiplication to match observed covariance scale
        return 5 * ret 
                
    def forward(self, x):
        """
        Compute trading weights based on Ornstein-Uhlenbeck process parameters.
        
        Args:
            x: Input tensor of cumulative residuals of shape (N, T) where N is batch size and T is time series length
            
        Returns:
            weights: Trading weights tensor of shape (N)
        """
        # Get the output device
        output_device = x.device

        # Assert that x is 2D
        assert len(x.shape) == 2, "Input to OUThreshold must be 2D (batch_size, sequence_length)"
        
        # Ensure input is float32 and on correct device
        x = x.to(dtype=torch.float, device=output_device)
        
        N, T = x.shape
        Ys = x[:, 1:]  # (N, T-1)
        Xs = x[:, :-1]
        
        # Calculate means
        if not self.use_robust_estimators:
            means_x = torch.mean(Xs, dim=1)  # N
            means_y = torch.mean(Ys, dim=1)
        else:
            means_x = self.robust_mean(Xs)
            means_y = self.robust_mean(Ys)
        
        # Calculate variances with epsilon to avoid division by zero
        eps = 1e-16
        if not self.use_robust_estimators:
            vars_x = torch.var(Xs, dim=1) + eps  # N
            vars_y = torch.var(Ys, dim=1) + eps
        else:
            vars_x = self.robust_variance(Xs) + eps
            vars_y = self.robust_variance(Ys) + eps
        
        # Calculate covariances
        if not self.use_robust_estimators:
            covs = torch.mean((Xs - means_x.reshape((N, 1))) * (Ys - means_y.reshape((N, 1))), dim=1)  # N
        else:
            covs = self.robust_covariance(Xs, Ys)
        
        # Calculate R² values
        r2 = covs**2 / (vars_x * vars_y)  # N
        
        # Calculate regression parameters
        betas = covs / vars_x  # N
        alphas = means_y - betas * means_x
        
        # Calculate long-term means
        mus = alphas / (1 - betas)
        
        # Create mask for valid beta values (between 0 and 1)
        mask = (betas > 0) & (betas < 1)  # N
        
        # Calculate residuals
        residuals = Ys - betas.reshape((N, 1)) * Xs - alphas.reshape((N, 1))  # (N, T-1)
        
        # Calculate volatilities
        sigmas = torch.sqrt(torch.var(residuals, dim=1) / torch.abs(1 - betas**2))  # N
        
        # Calculate trading signals; only trade if beta is between 0 and 1 and volatility is greater than epsilon
        mask = mask & (sigmas > eps) 
        signal = (mus - Ys[:, -1]) / sigmas  # N
        signal[~mask] = 0
        
        # Generate weights based on signal threshold
        weights = (signal > self.signal_threshold).to(dtype=torch.float) - (signal < (-self.signal_threshold)).to(dtype=torch.float)
        
        # Apply R² threshold filter
        weights = weights * (r2 > self.r2_threshold).to(dtype=torch.float)
        
        # Handle any remaining NaN values
        weights = torch.nan_to_num(weights, nan=0.0)
        
        return weights
