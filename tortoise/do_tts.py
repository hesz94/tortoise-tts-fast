# AGPL: a notification must be added stating that changes have been made to that file. 

import argparse
import os

import torch
import torchaudio

from api import TextToSpeech, MODELS_DIR
from utils.audio import load_voices
from utils.diffusion import K_DIFFUSION_SAMPLERS
SAMPLERS = list(K_DIFFUSION_SAMPLERS.keys()) + ['ddim']

from contextlib import contextmanager
from time import time
@contextmanager
def timeit(desc=''):
    start = time()
    yield
    print(f'{desc} took {time() - start:.2f} seconds')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', type=str, help='Text to speak.', default="The expressiveness of autoregressive transformers is literally nuts! I absolutely adore them.")
    parser.add_argument('--voice', type=str, help='Selects the voice to use for generation. See options in voices/ directory (and add your own!) '
                                                 'Use the & character to join two voices together. Use a comma to perform inference on multiple voices.', default='random')
    parser.add_argument('--preset', type=str, help='Which voice preset to use.', default='fast')
    parser.add_argument('--output_path', type=str, help='Where to store outputs.', default='results/')
    parser.add_argument('--model_dir', type=str, help='Where to find pretrained model checkpoints. Tortoise automatically downloads these to .models, so this'
                                                      'should only be specified if you have custom checkpoints.', default=MODELS_DIR)
    parser.add_argument('--candidates', type=int, help='How many output candidates to produce per-voice.', default=3)
    parser.add_argument('--seed', type=int, help='Random seed which can be used to reproduce results.', default=None)
    parser.add_argument('--produce_debug_state', type=bool, help='Whether or not to produce debug_state.pth, which can aid in reproducing problems. Defaults to true.', default=True)
    parser.add_argument('--cvvp_amount', type=float, help='How much the CVVP model should influence the output.'
                                                          'Increasing this can in some cases reduce the likelihood of multiple speakers. Defaults to 0 (disabled)', default=.0)
    parser.add_argument('--low_vram', dest='high_vram', help='re-enable default offloading behaviour of tortoise', default=True, action='store_false')
    parser.add_argument('--half', help='enable autocast to half precision for autoregressive model', default=False, action='store_true')
    parser.add_argument('--kv_cache', help='enable (partially broken) kv_cache usage, leading to drastic speedups but worse memory usage + results', default=False, action='store_true')
    parser.add_argument('--sampler', help='override the sampler used for diffusion (default depends on --preset)', choices=SAMPLERS)
    parser.add_argument('--steps', type=int, help='override the steps used for diffusion (default depends on --preset)')
    parser.add_argument('--cond_free', help='force conditioning free diffusion', action='store_true')
    parser.add_argument('--no_cond_free', help='force disable conditioning free diffusion', dest='cond_free', action='store_false')

    args = parser.parse_args()
    os.makedirs(args.output_path, exist_ok=True)

    tts = TextToSpeech(models_dir=args.model_dir, high_vram=args.high_vram, kv_cache=args.kv_cache)

    selected_voices = args.voice.split(',')
    for k, selected_voice in enumerate(selected_voices):
        if '&' in selected_voice:
            voice_sel = selected_voice.split('&')
        else:
            voice_sel = [selected_voice]
        voice_samples, conditioning_latents = load_voices(voice_sel)

        with timeit(f'Generating {args.candidates} candidates for voice {selected_voice} (seed={args.seed})'):
            nullable_kwargs = {
                k:v for k,v in zip(
                    ['sampler', 'diffusion_iterations', 'cond_free'],
                    [args.sampler, args.steps, args.cond_free]
                ) if v is not None
            }
            gen, dbg_state = tts.tts_with_preset(
                args.text, k=args.candidates, voice_samples=voice_samples, conditioning_latents=conditioning_latents,
                preset=args.preset, use_deterministic_seed=args.seed, return_deterministic_state=True, cvvp_amount=args.cvvp_amount,
                half=args.half, **nullable_kwargs
            )
        if isinstance(gen, list):
            for j, g in enumerate(gen):
                torchaudio.save(os.path.join(args.output_path, f'{selected_voice}_{k}_{j}.wav'), g.squeeze(0).cpu(), 24000)
        else:
            torchaudio.save(os.path.join(args.output_path, f'{selected_voice}_{k}.wav'), gen.squeeze(0).cpu(), 24000)

        if args.produce_debug_state:
            os.makedirs('debug_states', exist_ok=True)
            torch.save(dbg_state, f'debug_states/do_tts_debug_{selected_voice}.pth')

