import torch
import torch.nn as nn


class CNN_Block(nn.Module):
    """
    1D Convolutional block with residual connection and optional normalization.
    
    The block consists of two 1D convolution layers with ReLU activation and optional
    instance normalization. It includes a residual connection that adds the input
    to the output (with channel repetition if needed).
    
    Args:
        in_filters (int, optional): Number of input channels. Defaults to 1.
        out_filters (int, optional): Number of output channels. Defaults to 8.
        normalization (bool, optional): Whether to use instance normalization. Defaults to True.
        filter_size (int, optional): Size of the convolutional kernel. Defaults to 2.
    
    Tensor Shapes:
        - Input: (batch_size, in_filters, time_steps)
        - After conv1: (batch_size, out_filters, time_steps)
        - After conv2: (batch_size, out_filters, time_steps)
        - Output: (batch_size, out_filters, time_steps)
    """
    
    def __init__(self, in_filters: int = 1, out_filters: int = 8, normalization: bool = True, filter_size: int = 2):
        super(CNN_Block, self).__init__() 
        self.is_trainable = True
        self.is_frictions_model = False

        self.in_filters = in_filters
        self.out_filters = out_filters
        
        self.conv1 = nn.Conv1d(in_channels=in_filters, out_channels=out_filters, kernel_size=filter_size,
                                    stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros')
        self.conv2 = nn.Conv1d(in_channels=out_filters, out_channels=out_filters, kernel_size=filter_size,
                                    stride=1, padding=0, dilation=1, groups=1, bias=True, padding_mode='zeros')
        self.relu = nn.ReLU(inplace=True)
        self.left_zero_padding = nn.ConstantPad1d((filter_size-1,0),0)
        
        self.normalization1 = nn.InstanceNorm1d(in_filters)
        self.normalization2 = nn.InstanceNorm1d(out_filters)
        self.normalization = normalization
       
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass of the CNN block.
        
        Args:
            x (torch.Tensor): Input tensor of shape (batch_size, in_filters, time_steps)
        
        Returns:
            torch.Tensor: Output tensor of shape (batch_size, out_filters, time_steps)
            
        Processing Steps:
            1. Optional instance normalization on input
            2. Left zero padding to maintain temporal dimension
            3. First convolution + ReLU
            4. Optional instance normalization
            5. Second convolution + ReLU
            6. Residual connection (with channel repetition if needed)
        """
        if self.normalization:
            x = self.normalization1(x)
        out = self.left_zero_padding(x)
        out = self.conv1(out)
        out = self.relu(out)
        if self.normalization: 
            out = self.normalization2(out)
        out = self.left_zero_padding(out)
        out = self.conv2(out)
        out = self.relu(out)
        out = out + x.repeat(1,int(self.out_filters/self.in_filters),1)   
        return out 


class CNNTransformer(nn.Module):
    """
    A hybrid CNN-Transformer model for time series processing.
    
    This model combines 1D convolutional layers for feature extraction with
    a transformer encoder for temporal attention processing. The final output
    is a single value per input sequence.
    
    Args:
        logdir (str): Directory path for saving logs and checkpoints
        random_seed (int, optional): Seed for reproducibility. Defaults to 0.
        lookback (int, optional): Number of time steps to process. Defaults to 30.
        device (str, optional): Device to run the model on. Defaults to "cpu".
        normalization_conv (bool, optional): Use normalization in CNN blocks. Defaults to True.
        filter_numbers (list[int], optional): Number of filters for each CNN layer. Defaults to [1,8].
        attention_heads (int, optional): Number of attention heads in transformer. Defaults to 4.
        use_convolution (bool, optional): Whether to use CNN layers. Defaults to True.
        hidden_units (int, optional): Size of transformer's feedforward network. Defaults to 2*8.
        hidden_units_factor (int, optional): Alternative way to specify hidden_units as multiple of last CNN layer. Defaults to 2.
        dropout (float, optional): Dropout rate. Defaults to 0.25.
        filter_size (int, optional): Size of CNN kernels. Defaults to 2.
        use_transformer (bool, optional): Whether to use transformer layer. Defaults to True.
    
    Tensor Shapes:
        - Input: (batch_size, time_steps)
        - After reshape: (batch_size, 1, time_steps)
        - After CNN blocks: (batch_size, filter_numbers[-1], time_steps)
        - After permute: (time_steps, batch_size, filter_numbers[-1])
        - After transformer: (time_steps, batch_size, filter_numbers[-1])
        - Final output: (batch_size,)
    """

    def __init__(
        self,
        random_seed: int = 0,
        lookback: int = 30,
        device: str = "cpu",  # other options for device are e.g. "cuda:0"
        normalization_conv: bool = True,
        filter_numbers: list[int] = [1, 8],
        attention_heads: int = 4,
        use_convolution: bool = True,
        hidden_units: int = 2 * 8,
        hidden_units_factor: int = 2,
        dropout: float = 0.25,
        filter_size: int = 2,
        use_transformer: bool = True,
    ):
        super(CNNTransformer, self).__init__()
        self.is_trainable = True
        self.is_frictions_model = False

        if hidden_units and hidden_units_factor and hidden_units != hidden_units_factor * filter_numbers[-1]:
            raise Exception("`hidden_units` conflicts with `hidden_units_factor`; provide one or the other, but not both.")
        if hidden_units_factor:
            hidden_units = hidden_units_factor * filter_numbers[-1]
        self.random_seed = random_seed 
        torch.manual_seed(self.random_seed)
        self.device = torch.device(device)
        self.filter_numbers = filter_numbers
        self.use_transformer = use_transformer
        self.use_convolution = use_convolution and len(filter_numbers) > 0
        
        self.convBlocks = nn.ModuleList()
        for i in range(len(filter_numbers)-1):
            self.convBlocks.append(
                CNN_Block(filter_numbers[i], filter_numbers[i+1], normalization=normalization_conv, filter_size=filter_size)
            )
        self.encoder = nn.TransformerEncoderLayer(d_model=filter_numbers[-1], nhead=attention_heads, dim_feedforward=hidden_units, dropout=dropout)
        self.linear = nn.Linear(filter_numbers[-1],1)
        #self.softmax = nn.Sequential(nn.Linear(filter_numbers[-1],num_classes))#,nn.Softmax(dim=1))
                 
    def forward(self, x):
        """
        Forward pass of the CNN-Transformer network.
        
        Args:
            x (torch.Tensor): Input tensor of shape (batch_size, time_steps)
        
        Returns:
            torch.Tensor: Output predictions of shape (batch_size,)
            
        Processing Steps:
            1. Reshape input to (batch_size, 1, time_steps)
            2. Optional CNN processing:
               - Multiple CNN blocks transform (batch_size, C_in, time_steps) → (batch_size, C_out, time_steps)
               where C_in/C_out are the input/output channels specified in filter_numbers
            3. Permute to transformer format: (time_steps, batch_size, channels)
            4. Optional transformer processing maintaining shape
            5. Take final time step and project to scalar output
        """
        N,T = x.shape
        x = x.reshape((N,1,T))  # (N,1,T)
        if self.use_convolution:
            for i in range(len(self.filter_numbers)-1):
                x = self.convBlocks[i](x)  # (N,C,T) where C is the number of channels/features
        x = x.permute(2,0,1)  
        if self.use_transformer:
            x = self.encoder(x)  # the input of the transformer is (T,N,C)
        # self.softmax(x[-1,:,:])  # (N,num_classes)
        return self.linear(x[-1,:,:]).squeeze() # this outputs the weights
        