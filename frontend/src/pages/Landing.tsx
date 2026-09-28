import Hero from '../components/Landing/Hero';
import GuernseyStrip from '../components/Landing/GuernseyStrip';
import ProofCards from '../components/Landing/ProofCards';
import HowItThinks from '../components/Landing/HowItThinks';
import SundayArvo from '../components/Landing/SundayArvo';
import LandingFooter from '../components/Landing/LandingFooter';

const Landing = () => {
  return (
    <div>
      <Hero />
      <GuernseyStrip />
      <ProofCards />
      <HowItThinks />
      <SundayArvo />
      <LandingFooter />
    </div>
  );
};

export default Landing;
