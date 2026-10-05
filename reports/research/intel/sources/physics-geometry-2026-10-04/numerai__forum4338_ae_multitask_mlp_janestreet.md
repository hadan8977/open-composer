source: https://forum.numer.ai/t/autoencoder-and-multitask-mlp-on-new-dataset-from-kaggle-jane-street/4338
fetched_utc: 2026-10-04T18:46:42Z
bytes_raw: 80237

AutoEncoder and multitask MLP on new dataset (from Kaggle Jane Street) - Data Science - Numerai Forum

= 40rem)" rel="stylesheet" data-target="discourse-ai_desktop"  />

= 40rem)" rel="stylesheet" data-target="discourse-reactions_desktop"  />

= 40rem)" rel="stylesheet" data-target="poll_desktop"  />

      AutoEncoder and multitask MLP on new dataset (from Kaggle Jane Street)

                Data Science

                jrai

                    October 15, 2021,  2:54pm

              1

The top submission to the Kaggle Jane Street competition winner posted their models and some discussion. Numerai and that Kaggle competition are fairly similar using low signal market data and you can also use multiple targets to predict just one target on which you’re ultimately scored. The initial idea for this model architecture came from this notebook and this paper (Deep Bottleneck Classifiers in Supervised Dimension Reduction).

The author of the initial code explains “The idea of using an encoder is to denoise the data.” The competition winner, Yirun Zhang explains the model really well (I’ve made a few edits so it’s more applicable to the Numerai dataset):

"Deep Learning Model:

Use autoencoder to create new features, concatenating with the original features as the input to the downstream MLP model

Train autoencoder and MLP together

Add target information to autoencoder (supervised learning) to force it to generate more relevant features, and to create a shortcut for backpropagation of gradient

Add Gaussian noise layer before encoder for data augmentation and to prevent overfitting

Use swish activation function instead of ReLU to prevent ‘dead neuron’ and smooth the gradient

Batch Normalisation and Dropout are used for MLP

Only monitor the MSE loss of MLP instead of the overall loss for early stopping"

Here is Yirun’s diagram:

image732×546 8.84 KB

The Numerai architecture is the same, but we can just use regression loss functions instead of classification loss functions (i.e. MSE instead of BCE). Also, we can use a different number of targets. For example, you can have the model predict all of the 20 day targets at once and then the final prediction would be the mean of all of those predictions. My artistic interpretation of how it would look for Numerai:

image882×808 152 KB

The model outputs 3 different vectors: 1) it tries to recreate the feature vector after passing through an autoencoder to compress the feature space into a latent space. 2) it uses the decoder from the autoencoder to try to predict the targets (so it can generate more relevant features in the latent space) and 3) it uses a normal MLP to try to predict the multiple targets at once which can be averaged or ensembled for a final prediction.

With some hyperparameter searches, slightly different from the ones in the code below, initial results on validation (with zero feature neutralization) look quite good and fairly different from the new data’s example predictions:

image705×572 65.3 KB

Next steps and other thoughts:

Tune hyperparameters with Optuna

Ensemble CV folds and multiple models

Try different combinations of loss functions and targets

Train each era as a batch (use tf.keras.utils.Sequence)

Try different combinations of ensembling the target outputs

Here is the modified code for Numerai predictions from Yirun’s notebook to get you started, but you may need a few dependencies and other variable definitions. There may be errors or things that can be done better, appreciate any input:

def create_architecture(num_columns, num_labels, hidden_units, dropout_rates, lr=1e-3):
    tf.keras.backend.clear_session()

    inp = tf.keras.layers.Input(shape=(num_columns,))
    x0 = tf.keras.layers.BatchNormalization()(inp)

    encoder = tf.keras.layers.GaussianNoise(dropout_rates[0])(x0)
    encoder = tf.keras.layers.Dense(hidden_units[0])(encoder)
    encoder = tf.keras.layers.BatchNormalization()(encoder)
    encoder = tf.keras.layers.Activation("swish")(encoder)

    decoder = tf.keras.layers.Dropout(dropout_rates[1])(encoder)
    decoder = tf.keras.layers.Dense(num_columns, name="decoder")(decoder)

    x_ae = tf.keras.layers.Dense(hidden_units[1])(decoder)
    x_ae = tf.keras.layers.BatchNormalization()(x_ae)
    x_ae = tf.keras.layers.Activation("swish")(x_ae)
    x_ae = tf.keras.layers.Dropout(dropout_rates[2])(x_ae)

    out_ae = tf.keras.layers.Dense(num_labels, activation="sigmoid", name="ae_targets")(
        x_ae
    )

    x = tf.keras.layers.Concatenate()([x0, encoder])
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Dropout(dropout_rates[3])(x)

    for i in range(2, len(hidden_units)):
        x = tf.keras.layers.Dense(hidden_units[i])(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.Activation("swish")(x)
        x = tf.keras.layers.Dropout(dropout_rates[i + 2])(x)

    out = tf.keras.layers.Dense(num_labels, activation="sigmoid", name="targets")(x)

    model = tf.keras.models.Model(inputs=inp, outputs=[decoder, out_ae, out])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
        loss={
            "decoder": tf.keras.losses.MeanSquaredError(),  # how does the decoder do on translating back to features
            "ae_targets": tf.keras.losses.MeanSquaredError(),  # how does the decoder do with predicting targets
            "targets": tf.keras.losses.MeanSquaredError(),
        },
    )

    return model

targets = [
    "target_nomi_20",
    "target_jerome_20",
    "target_janet_20",
    "target_ben_20",
    "target_alan_20",
    "target_paul_20"
]

model_name = f"keras_{datetime.now().strftime('%s')}"

params = {
    "num_columns": len(feature_names),
    "num_labels": len(targets),
    "hidden_units": [96, 96, 896, 448, 448, 256],
    "dropout_rates": [
        0.035,
        0.035,
        0.4,
        0.1,
        0.4,
        0.3,
        0.25,
        0.4,
    ],
    "lr": 1e-4,
}

model = create_architecture(**params)

history = model.fit(
    X =  train_data[feature_names].values
    y = [train_data[feature_names].values,
        train_data[targets].values,
        train_data[targets].values]
    epochs=1,
)

                25 Likes

                      What is good models for numerai signals?

                      Numerai Self-Supervised Learning & Data Augmentation Projects

                      Numerai Self-Supervised Learning & Data Augmentation Projects

                yxbot

                    October 15, 2021,  3:51pm

              2

I have been using DAE on the legacy dataset, but haven’t got around to tailor it for the new dataset, for what it is worth, here is the python class that I have been using in Pytorch:

class Denoise_Autoencoder(nn.Module):
def __init__(self, in_dimension, embedding_dimension=10):
    super().__init__()
    self.encoder = nn.Sequential(
        nn.Dropout(p=0.1),
        nn.Linear(in_dimension, 256),
        nn.BatchNorm1d(256),
        nn.Hardswish(),
        nn.Dropout(p=0.1),
        nn.Linear(256, 128),
        nn.BatchNorm1d(128),
        nn.Hardswish(),
        nn.Dropout(p=0.1),
        nn.Linear(128, embedding_dimension),)
    self.decoder = nn.Sequential(
        nn.BatchNorm1d(embedding_dimension),
        nn.Hardswish(),
        nn.Dropout(p=0.1),
        nn.Linear(embedding_dimension, 128),
        nn.BatchNorm1d(128),
        nn.Hardswish(),
        nn.Dropout(p=0.1),
        nn.Linear(128, 256),
        nn.BatchNorm1d(256),
        nn.Hardswish(),
        nn.Dropout(p=0.1),
        nn.Linear(256, in_dimension),)
def forward(self, x):
    embedding = self.encoder(x)
    decode = self.decoder(embedding)
    return embedding, decode

from a crude first look, seems the only significant difference from Yirun’s approach is their use of Gaussian noise, which I shall try in due time.

Another departure of my own approach is that I extracted the features, concat them with original feature - it was ok with the old dataset, not sure about the new one - and run it via lightgbm on different tree models

                10 Likes

                jrai

                    October 15, 2021,  4:35pm

              3

The autoencoders look very similar. Are you training on an era by era basis?

There is a lot you can do with the latent space (using it as features for other models, concatenating it to a subset of features, etc.). The multitask training and combination with autoencoder being trained at the same time just seemed particularly elegant in this case.

                1 Like

                yxbot

                    October 15, 2021,  4:41pm

              4

I kind of used a “stupid and dumb” approach, so feature generation with DAE is a completely separate step from training pipeline. I just extracted the middle layer - the last layer of the encoder - but for this, it became unsupervised learning and I do it on train+val+test- all in one go.  I then use the DAE model to generate features for each live round.

On the actually model training under supervised learning context, i.e. with target, basically repeated CV on separated eras - I didn’t even do timesplit for any of my legacy models - they still do quite ok.

For the new dataset, yes I completely agree there are tones of things to try alongside this direction 

                jrai

                    October 15, 2021,  4:45pm

              5

That is a good idea. For this model, the autoencoder could still be pre-trained or fine-tuned on train+val+test as well to leverage the full unsupervised data. Although it would add leakage in validation stats.

                yxbot

                    October 15, 2021,  4:48pm

              6

 jrai:

Although it would add leakage in validation stats.

I doubt - this is Qinong’s abysmal diagnostics 

image291×510 17.2 KB

                hedgingcat

                    October 16, 2021,  6:50pm

              7

Glad to see my solution being discussed here. The unsupervised autoencoder without label information can be trained on train+valid+test, however, the supervised version in my solution should take extra care due to label leakage. So, I trained it in every fold to prevent leakage.

BTW, the highlight in my winning solution is the sample weight training which gives a boost to both public and private scores. But I am not sure if it can be useful in Numerai.

                12 Likes

                sunkay

                    October 19, 2021,  8:14am

              8

The feature vector compressed by the encode is just another version of the original features, I don’t understand why it could makes the model better.

                1 Like

                perfect_fit

                    October 28, 2021, 11:26am

              9

Nice! Was pretty blown away when I saw the 1st place solution for Jane Street. Last time I saw someone win a tabular Kaggle competition with pure NNs was Porto Seguro 4 years ago, which also used denoising autoencoders.

Very cool to see that you implemented this for Numerai @jrai ! @hedgingcat, nice to see that you are also part of the Numerai community! 

                1 Like

                luee

                    October 28, 2021,  3:13pm

              10

 hedgingcat:

BTW, the highlight in my winning solution is the sample weight training which gives a boost to both public and private scores. But I am not sure if it can be useful in Numerai.

Depending on your cross-val scheme I would be wary of adding the valid + test data in the autoencoder loop, you don’t want to test a model on data in 2018 that uses 2020 data for dimensionality reduction.

                danzell

                    November 8, 2021,  8:25am

              11

Here is some further autoencoder stuff. I used a DAE in TPS Jan 21 & Feb 21 Competitions @kaggle.

Write up Jan:

link to write up

Write up Feb:

link to write up

                2 Likes

                stoicism

                    December 23, 2021, 12:17pm

              12

 jrai:

Use autoencoder to create new features, concatenating with the original features as the input to the downstream MLP model

Can anyone explain this? Autoencoder is a lower dimensional representation of the original features, how concatenating those contribute to improved performance by the MLP?

                jrai

                    December 23, 2021,  2:43pm

              13

The autoencoder is trying to do dimensionality reduction (compression), and in that goal it may be doing noise reduction. The jargon to describe this autoencoder is a bottleneck denoising autoencoder. There’s a bunch of prior literature on why it might be beneficial to create a latent space for training a downstream model and to “learn” feature engineering. You may not even have to concatenate the latent space to the original features, you can also experiment with just using the latent space as features (at which point you should also still learn it end to end).

Here are a couple of articles and quotes from them:

“With this approach, our model isn’t able to simply develop a mapping which memorizes the training data because our input and target output are no longer the same. Rather, the model learns a vector field for mapping the input data towards a lower-dimensional manifold (recall from my earlier graphic that a manifold describes the high density region where the input data concentrates); if this manifold accurately describes the natural data, we’ve effectively “canceled out” the added noise.”

Introduction to autoencoders.

Autoencoders are an unsupervised learning technique in which we leverage neural
networks for the task of representation learning. Specifically, we'll design a
neural network architecture such that we impose a bottleneck in the network
which forces a...

“Autoencoders are used for Noise Removal: If we can pass the noisy data as input and clean data as output and train an autoencoder on such given data pairs, trained Autoencoders can be highly useful for noise removal. This is because noise points usually do not have any correlations. Now, as the autoencoders need to represent the data in the lowest dimensions, the encodings usually have only the important relations there exists, rejecting the random ones. So, the decoded data coming out as output of an autoencoder is free of all the extra relations and hence the noise.”

https://towardsdatascience.com/introduction-to-autoencoders-7a47cf4ef14b

                1 Like

                stoicism

                    December 23, 2021,  8:06pm

              14

Thanks for the references, much appreciated. I am familiar with Autoencoders and their noise reduction capability. I was just wondering how appending the encoded features with the original one provides performance boost. What if we don’t append at all and only use the encoded and denoised features only? I have seen several examples where the features were reduced based on correlation matrix. I also have seen examples where PCA was used to claimed to not have performed well, probably since PCA only accounts for linear relationships where autoencoders are much more general.

                gbrecht

                    December 25, 2021, 10:40am

              15

I fed my DAE features to the example model and the results were very bad. Maybe my DAE was bad, but it made me ditch the idea of training on reduced features only

                1 Like

                olivepossum

                    January 1, 2022,  9:14am

              16

Thanks for sharing @jrai, super interesting!

I’ve tried to port to PyTorch the architecture mentioned in the post (not much success in terms of performance but nothing tuned yet). The code is quite verbose but should behave very similar than the the Keras one.

Not a PyTorch expert (as you’ll notice looking at the code) so any feedback, suggestion, correction or bug spotted is very appreciated.

The architecture looks like this:

targets = ["target_nomi_20", "target_jerome_20", "target_janet_20", "target_ben_20", "target_alan_20", "target_paul_20"]
inp = len(feature_names) 
targets_len = len(targets)

hidden_units = [96, 96, 896, 448, 448, 256]
dropout_rates = [0.035, 0.035, 0.4, 0.1, 0.4, 0.3, 0.25, 0.4]
lr = 0.0001

concatenated_input = inp + hidden_units[0]

class AEMLP(nn.Module):
  def __init__(self):
      super(AEMLP, self).__init__()

      #encoder
      self.gaussian_noise = GaussianNoise(dropout_rates[0])
      self.batchnorm1_encoder = nn.BatchNorm1d(inp)
      self.linear_encoder = nn.Linear(inp, hidden_units[0], bias=True)
      self.batchnorm2_encoder = nn.BatchNorm1d(hidden_units[0])
      self.hardswish = nn.Hardswish()

      #decoder
      self.dropout_decoder = nn.Dropout(dropout_rates[1])
      self.linear_decoder = nn.Linear(hidden_units[0], inp, bias=True)

      #x_ae - decoder predicting targets
      self.linear_x_ae = nn.Linear(inp, hidden_units[1], bias=True)
      self.batchnorm_x_ae = nn.BatchNorm1d(hidden_units[1])
      self.dropout_x_ae = nn.Dropout(dropout_rates[2])
      self.linear_out_ae = nn.Linear(hidden_units[1], targets_len, bias=True)
      self.sigmoid_x_ae = nn.Sigmoid()

      #x - mlp predictions
      self.batchnorm1_x = nn.BatchNorm1d(concatenated_input)
      self.dropout_x1 = nn.Dropout(dropout_rates[3])

      self.layers = nn.ModuleList()
      prev_dim = concatenated_input
      for i in range(2, len(hidden_units)):
          self.layers.append(nn.Linear(prev_dim, hidden_units[i], bias=True))
          self.layers.append(nn.BatchNorm1d(hidden_units[i]))
          self.layers.append(nn.Hardswish())
          self.layers.append(nn.Dropout(dropout_rates[i + 2]))
          prev_dim = hidden_units[i]

      self.linear_x_out = nn.Linear(prev_dim, targets_len, bias=True)
      self.sigmoid_x = nn.Sigmoid()

      #init linear layers
      torch.nn.init.xavier_uniform_(self.linear_encoder.weight)
      torch.nn.init.xavier_uniform_(self.linear_decoder.weight)
      torch.nn.init.xavier_uniform_(self.linear_x_ae.weight)
      torch.nn.init.xavier_uniform_(self.linear_out_ae.weight)
      torch.nn.init.xavier_uniform_(self.linear_x_out.weight)
      for layer in self.layers:
        if isinstance(layer, nn.Linear):
            torch.nn.init.xavier_uniform_(layer.weight.data)
            if layer.bias is not None:
                torch.nn.init.zeros_(layer.bias)

  def forward(self, inpu): 
      #encoder 
      x0 = self.batchnorm1_encoder(inpu)

      encoder = self.gaussian_noise(x0)
      encoder = self.linear_encoder(encoder)
      encoder = self.batchnorm2_encoder(encoder)
      encoder = self.hardswish(encoder)

      #decoder 
      decoder = self.dropout_decoder(encoder)
      out_decoder = self.linear_decoder(decoder)

      #x_ae 
      x_ae = self.linear_x_ae(out_decoder)
      x_ae = self.batchnorm_x_ae(x_ae)
      x_ae = self.hardswish(x_ae)
      x_ae = self.dropout_x_ae(x_ae)
      x_ae = self.linear_out_ae(x_ae)
      out_ae = self.sigmoid_x_ae(x_ae)

      #mlp predictions 
      x = torch.cat((x0, encoder), 1)
      x = self.batchnorm1_x(x)
      x = self.dropout_x1(x)

      for layer in self.layers:
        x = layer(x)      
      x = self.linear_x_out(x)
      out = self.sigmoid_x(x)

      return out_decoder, out_ae, out

Then we need three loss functions:

func_loss_out_decoder = nn.MSELoss().cuda()
func_loss_out_ae = nn.MSELoss().cuda()
func_loss_out = nn.MSELoss().cuda()

Iterations over epochs and batches calculating the global loss would look like this (just included the relevant part of the loop code):

for epoch in epochs:
      for era in eras:  
            batch_count += 1
            x, y = get_data(era)
            out_decoder, out_ae, out = aemlp(x)
            loss_out_decoder = func_loss_out_decoder(out_decoder, x)
            loss_out_ae = func_loss_out_ae(out_ae, y)
            loss_out = func_loss_out(out, y)
            loss = (loss_out_decoder + loss_out_ae + loss_out)/3
            loss.backward()
            optimizer.step() 
      acc_loss_train += loss
loss_train = acc_loss_train / batch_count
check_early_stopping(validation_data)

In early stopping, just use func_loss_out to calculate the loss.

Finally, a class to generate Gaussian Noise:

class GaussianNoise(nn.Module):
    def __init__(self, sigma=0.1, is_relative_detach=True):
        super().__init__()
        self.sigma = sigma
        self.is_relative_detach = is_relative_detach
        self.register_buffer('noise', torch.tensor(0))

    def forward(self, x):
        if self.training and self.sigma != 0:
            scale = self.sigma * x.detach() if self.is_relative_detach else self.sigma * x
            sampled_noise = self.noise.expand(*x.size()).float().normal_() * scale
            x = x + sampled_noise
        return x 

                6 Likes

                gbrecht

                    January 1, 2022,  8:52pm

              17

I hope it is okay to ask a few questions.

Do I understand correctly that your encoder does Normalization => Noise => Linear ==> Normalization ==> Activation ? If so, why two times activation? Do you think one layer is enough?

Is there a special reason your decoder is not a mirror of your encoder?

Why no normalization on the decoder?

I am sure I have more once I understand more, thx

                maxchu

                    January 1, 2022, 11:15pm

              18

Can you reproduce the same validation result as @jrai ?

                olivepossum

                    January 1, 2022, 11:58pm

              19

At the moment, not at all. There might be something wrong in my code

                jrai

                    January 2, 2022,  4:12pm

              20

 gbrecht:

Do I understand correctly that your encoder does Normalization => Noise => Linear ==> Normalization ==> Activation ? If so, why two times activation? Do you think one layer is enough?

Is there a special reason your decoder is not a mirror of your encoder?

Why no normalization on the decoder?

These architecture questions are probably better for @hedgingcat and I’d also be curious to hear thoughts from @jrb or @mdo

 maxchu:

Can you reproduce the same validation result as @jrai ?

The validation results I posted are after a fair amount of hp tuning, playing with different loss functions, number of layers, etc (so it’s also possible the validation results are just wildly overfit). I think the code provided is a very good starting point though.

                2 Likes

            next page →

    Related topics

          Topic

          Replies
          Views
          Activity

                Numerai Self-Supervised Learning & Data Augmentation Projects

                      Data Science

              114

              12523

              March 22, 2023

                NN architecture for >0.03 CORR on validation set

                      Data Science

              52

              9076

              August 26, 2021

                Using Transformers on Numerai's stock market data

                      Data Science

              22

              6464

              December 22, 2023

                Feature reversing input noise

                      Data Science

              21

              6487

              May 18, 2021

                Liz Experiment Review Q1 2021 : Generating Features and Applying Feature Neutralization

                      Tournament

              24

              5692

              May 11, 2021