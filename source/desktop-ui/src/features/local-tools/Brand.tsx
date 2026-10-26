import icon from '../../assets/bogo-tools-icon.png';
import './brand.css';

export function BrandIcon({className=''}:{className?:string}){
 return <img src={icon} alt="" draggable={false} className={'kio-brand-icon '+className}/>;
}

export function BrandWordmark({className=''}:{className?:string}){
 return <span className={'kio-brand-wordmark '+className}>Bogo Tools</span>;
}
